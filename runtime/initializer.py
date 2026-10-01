"""
--------------------------------------------
HERCULE AI Operating System
Runtime Initializer
--------------------------------------------
"""

from kernel.kernel import Kernel

from brain.brain import Brain

from orchestrator.orchestrator import Orchestrator

from memory.memory_manager import MemoryManager

from knowledge.knowledge_manager import KnowledgeManager

from models.model_manager import ModelManager

from abilities.ability_manager import AbilityManager

from perception.perception_manager import PerceptionManager

from communication.communication_manager import CommunicationManager

from security.security_manager import SecurityManager

from system.system_manager import SystemManager

from cognition.cognition_manager import CognitionManager

from engineering.engineering_manager import EngineeringManager

from robotics.robotics_manager import RoboticsManager

from simulation.simulation_manager import SimulationManager

from plugin_sdk.plugin_manager import PluginManager

from profiles.profile_manager import ProfileManager

from scripts.script_manager import ScriptManager

import logging

from pathlib import Path

logger = logging.getLogger("HERCULE.Runtime")


class RuntimeInitializer:

    def initialize(self, embedding_config=None, semantic_config=None):

        services = {}

        ##################################################
        # Core
        ##################################################

        services["kernel"] = Kernel()

        services["memory"] = MemoryManager()

        services["knowledge"] = KnowledgeManager()

        services["models"] = ModelManager()

        ##################################################
        # Embeddings (optional, configuration-driven)
        ##################################################

        if embedding_config is not None:
            from system.config.embedding_config import load_embedding_config
            from system.startup_validation import validate_startup
            from models.embeddings.cache import EmbeddingCache
            from models.embeddings.embedding_manager import EmbeddingManager

            if not hasattr(embedding_config, "provider"):
                embedding_config = load_embedding_config(dict(embedding_config))
            provider, report = validate_startup(embedding_config)
            services["embeddings"] = EmbeddingManager(
                providers={provider.model_id: provider},
                default_model=provider.model_id,
                cache=EmbeddingCache(version=embedding_config.cache_version),
                batch_size=embedding_config.batch_size,
                use_cache=bool(embedding_config.cache),
            )
            services["embedding_report"] = report

        services["abilities"] = AbilityManager()

        services["perception"] = PerceptionManager()

        services["communication"] = CommunicationManager()

        services["security"] = SecurityManager()

        services["system"] = SystemManager()

        ##################################################
        # Advanced
        ##################################################

        # Cognition requires references to models and memory
        services["cognition"] = CognitionManager(
            services["models"],
            services["memory"],
        )

        services["engineering"] = EngineeringManager()

        services["robotics"] = RoboticsManager()

        services["simulation"] = SimulationManager()

        services["plugins"] = PluginManager()

        services["profiles"] = ProfileManager()

        services["scripts"] = ScriptManager()

        ##################################################
        # Orchestrator
        ##################################################

        services["orchestrator"] = Orchestrator(

            memory=services["memory"],

            knowledge=services["knowledge"],

            models=services["models"],

            abilities=services["abilities"],

            perception=services["perception"],

            communication=services["communication"],

            security=services["security"],

            system=services["system"],

        )

        ##################################################
        # Brain
        ##################################################

        services["brain"] = Brain(

            services["orchestrator"]

        )

        ##################################################
        # Authoritative ExperienceManager (UAI L2) — ONE store shared
        # by Brain, Cognition, and SkillManager. Brain's autonomy
        # stack reuses ``brain._experience`` when present instead of
        # constructing its own, so no duplicate stores exist.
        ##################################################

        try:
            from cognition.experience.experience_manager import ExperienceManager

            _experience = ExperienceManager()
            try:
                _experience.load(services["brain"]._experience_path())
            except Exception as _exp_load_exc:
                logger.warning("experience store unreadable: %s", _exp_load_exc)
            services["experience"] = _experience
            services["brain"]._experience = _experience
            services["cognition"].experience = _experience
        except Exception as _exp_exc:
            logger.warning("experience manager unavailable: %s", _exp_exc)

        ##################################################
        # Research engine (UAI §23) — needs Brain; reuses the
        # registered web/search ability as its real source.
        ##################################################

        try:
            from cognition.research import ResearchEngine

            # Abilities register lazily inside Brain; prime them with the
            # same idempotent call Brain uses so the source lookup works.
            _abilities = services["abilities"]
            if hasattr(_abilities, "ensure_defaults"):
                _abilities.ensure_defaults()
            _research_source = _abilities.registry.get("web") \
                or _abilities.registry.get("search")
            services["research"] = ResearchEngine(
                source_ability=_research_source,
                brain=services["brain"],
            )
        except Exception as _research_exc:
            logger.warning("research engine unavailable: %s", _research_exc)

        ##################################################
        # Skill system (UAI §21/§22) — after Brain/Orchestrator so the
        # event bus and experience manager both exist.
        ##################################################

        try:
            from cognition.skills import SkillManager
            from system.paths import resolve_data_path

            _skills_default = Path(resolve_data_path("data/skills/skills.json"))
            try:
                from system.config.runtime_config import load_runtime_config as _load_rc

                _skills_configured = str(_load_rc().skills_store or "").strip()
            except Exception:
                _skills_configured = ""
            _skill_store = Path(_skills_configured) if _skills_configured else _skills_default
            services["skills"] = SkillManager(
                ability_manager=services["abilities"],
                experience_manager=services.get("experience"),
                store_path=_skill_store,
                event_bus=getattr(services["orchestrator"], "event_bus", None),
            )
            services["skills"].load()
        except Exception as _skill_exc:
            logger.warning("skill manager unavailable: %s", _skill_exc)

        ##################################################
        # Planner ↔ SkillManager (UAI L1) — validated skills only.
        #
        # The planner consults validated skill procedures for
        # goal-derived plans; every skill-built step still passes
        # capability validation, tool matching, policy, autonomy
        # gates, and verification. No manager is duplicated.
        ##################################################

        try:
            _skills = services.get("skills")
            if _skills is not None:
                services["brain"].authoritative_planner.configure_skills(_skills)
                services["cognition"].planner.configure_skills(_skills)
        except Exception as _skill_wire_exc:
            logger.warning("skill wiring unavailable: %s", _skill_wire_exc)

        ##################################################
        # Task -> Memory/World synchronization (v2)
        #
        # TaskManager stays the single authority for task state;
        # these subscribers only mirror terminal/pause/resume events
        # into memory summaries + world references (dedupe-safe, so
        # Brain's own end-of-cycle recording never double-counts).
        ##################################################

        try:
            _bus = getattr(services["orchestrator"], "event_bus", None)
            _memory = services.get("memory")
            _brain = services.get("brain")
            if _bus is not None and hasattr(_bus, "subscribe"):

                def _task_terminal(payload, _status=""):
                    try:
                        if not isinstance(payload, dict):
                            return
                        task_id = str(payload.get("task_id", ""))
                        if not task_id:
                            return
                        event = {"task_id": task_id, "status": _status,
                                 "goal": str(payload.get("goal", "")),
                                 "metadata": {"goal": str(payload.get("goal", ""))}}
                        if _memory is not None and hasattr(_memory, "remember_event"):
                            _memory.remember_event(event)
                        world = getattr(_brain, "world", None)
                        if world is not None and hasattr(world, "observe"):
                            tasks = getattr(
                                getattr(_brain, "orchestrator", None),
                                "task_manager", None)
                            goal = event["goal"]
                            try:
                                live = tasks.get(task_id) if tasks is not None else None
                                if isinstance(live, dict):
                                    goal = str((live.get("metadata", {}) or {}).get(
                                        "goal", "") or goal)[:200]
                            except Exception:
                                pass
                            world.observe("task", "task", goal or task_id,
                                          {"status": _status, "task_id": task_id},
                                          f"task {task_id} {_status}",
                                          confidence=0.9, verified=True)
                    except Exception:
                        pass

                for _event, _status in (("TaskCompleted", "COMPLETED"),
                                        ("TaskFailed", "FAILED"),
                                        ("TaskCancelled", "CANCELLED")):
                    _bus.subscribe(_event,
                                   lambda payload, _s=_status: _task_terminal(payload, _s))

                def _task_pause_resume(payload, _status=""):
                    try:
                        if not isinstance(payload, dict):
                            return
                        task_id = str(payload.get("task_id", ""))
                        if not task_id:
                            return
                        world = getattr(_brain, "world", None)
                        if world is not None and hasattr(world, "observe"):
                            world.observe("task", "task", task_id,
                                          {"status": _status, "task_id": task_id},
                                          f"task {task_id} {_status}",
                                          confidence=0.7)
                    except Exception:
                        pass

                for _event, _status in (("TaskPaused", "PAUSED"),
                                        ("TaskResumed", "RUNNING")):
                    _bus.subscribe(_event,
                                   lambda payload, _s=_status: _task_pause_resume(payload, _s))
        except Exception:
            pass

        ##################################################
        # Local model discovery (Ollama)
        #
        # Reports the real provider/model at startup. When Ollama is
        # unreachable or has no models, this logs a clear operator
        # message (including the `ollama serve` hint when the binary
        # exists but the server is down). Nothing is auto-installed;
        # model requests then fail honestly per call.
        ##################################################

        try:
            import logging as _logging
            import shutil as _shutil

            _init_log = _logging.getLogger("hercule.runtime")
            _discovery = services["models"].discover_models()
            _installed = _discovery.get("installed_ollama_models", [])
            services["model_discovery"] = _discovery
            if _installed:
                _init_log.info(
                    "local LLM ready: provider=[ollama] model=[%s] installed=%s",
                    services["models"].default_model, _installed,
                )
            else:
                _hint = ""
                if _shutil.which("ollama"):
                    _hint = " Ollama is installed but not running; start it with `ollama serve`."
                else:
                    _hint = (" Ollama is not reachable at "
                             f"{services['models'].ollama_host}.")
                _init_log.warning(
                    "local LLM unavailable: no Ollama models discovered.%s"
                    " Model requests will return honest model-unavailable errors.",
                    _hint,
                )
        except Exception as exc:
            import logging as _logging

            _logging.getLogger("hercule.runtime").warning(
                "model discovery failed: %s", exc,
            )

        ##################################################
        # Semantic Capability Intelligence (Phase M)
        #
        # Activation rules — wired ONLY when at least one is true:
        #   1. ``semantic_config`` kwarg was explicitly passed by caller
        #   2. ``HERCULE_SEMANTIC_ENABLED=true`` was set in env
        #      (i.e. ``config.enabled`` is True)
        #   3. ``HERCULE_SEMANTIC_REQUIRED=true`` was set in env
        #      (i.e. ``config.required`` is True)
        #
        # When none of these hold, we skip the entire semantic stack
        # so legacy deterministic-only behavior remains byte-identical.
        ##################################################

        services["semantic_config"] = None
        services["semantic_proposer"] = None

        explicit_request = semantic_config is not None

        try:
            from system.config.semantic_config import (
                load_semantic_config,
                SemanticConfig,
            )
            if isinstance(semantic_config, SemanticConfig):
                semantic_overrides = semantic_config.as_dict()
            elif isinstance(semantic_config, dict):
                semantic_overrides = dict(semantic_config)
            else:
                semantic_overrides = {}
            config = load_semantic_config(overrides=semantic_overrides)
        except Exception:
            config = None

        if config is not None:
            services["semantic_config"] = config

        should_enable = (
            explicit_request
            or (config is not None and config.enabled)
            or (config is not None and config.required)
        )

        if should_enable and config is not None:
            try:
                from cognition.capabilities.semantic import SemanticCapabilityProposer
                from cognition.capabilities.inference import infer_capabilities
                from cognition.capabilities.registry import CapabilityRegistry
                from cognition.capabilities.capability import Capability

                registry = CapabilityRegistry()
                abilities = services["abilities"]
                try:
                    registry.register_default_tools(
                        abilities if hasattr(abilities, "get") else None,
                    )
                except Exception:
                    pass

                allowed_capabilities = [c.value for c in Capability]

                def deterministic_fn(task, ctx, untrusted):
                    return infer_capabilities(task)

                models = services["models"]
                proposer = SemanticCapabilityProposer(
                    model=models,
                    router=getattr(models, "router", None),
                    prompt_manager=None,
                    allowed_capabilities=allowed_capabilities,
                    enabled=bool(config.enabled or explicit_request),
                    required=bool(config.required),
                    shadow=bool(config.shadow),
                    min_confidence=float(config.min_confidence),
                    low_confidence=str(config.low_confidence),
                    max_retries=int(config.max_retries),
                    timeout_s=float(config.timeout_s) if config.timeout_s else None,
                    deterministic_fn=deterministic_fn,
                )
                services["semantic_proposer"] = proposer

                brain = services["brain"]
                policy = getattr(abilities, "policy", None)
                brain.configure_semantic(
                    config=config,
                    proposer=proposer,
                    registry=registry,
                    policy=policy,
                    ability_manager=abilities,
                )
            except Exception as exc:
                import logging

                logging.getLogger("hercule.runtime").warning(
                    "semantic capability wiring failed, falling back to"
                    " deterministic-only: %s",
                    exc,
                )
                services["semantic_proposer"] = None

        return services