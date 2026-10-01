from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Desktop Application (Stage 9)
Author: Heeran Paul
License: MIT
--------------------------------------------

JARVIS-style desktop control interface (tkinter, stdlib only).

Presentation only: every value on screen comes from
HerculeAppController snapshots of the live runtime. The UI thread
never blocks on the model — submissions run in a worker thread and
results return through a queue. No brain logic lives here.
"""

import queue
import threading
import tkinter as tk
from tkinter import scrolledtext, ttk

# Plugin panel (added for plugin platform)
try:
    from plugin_sdk.ui_panel import PluginPanel
    PLUGIN_PANEL_AVAILABLE = True
except Exception:
    PLUGIN_PANEL_AVAILABLE = False

BG = "#0a0e14"
PANEL = "#11161f"
ACCENT = "#00d4ff"
TEXT = "#c9e4f2"
DIM = "#5a6b7c"
GOOD = "#00e676"
WARN = "#ffab40"
BAD = "#ff5252"

STATE_COLORS = {
    "IDLE": DIM, "ACTIVE": ACCENT, "LISTENING": ACCENT,
    "UNDERSTANDING": ACCENT, "RECALLING": ACCENT, "REASONING": ACCENT,
    "PLANNING": WARN, "DECIDING": WARN, "EXECUTING": WARN,
    "OBSERVING": WARN, "VERIFYING": WARN, "REFLECTING": GOOD,
    "RECOVERING": BAD, "WAITING": WARN, "COMPLETED": GOOD,
    "SPEAKING": ACCENT, "ERROR": BAD, "UNKNOWN": DIM,
}


class HerculeDesktopApp:
    """Tk root window bound to a live HerculeAppController."""

    def __init__(self, controller, root=None, voice=None):
        self.controller = controller
        self.voice = voice  # optional VoiceController (v1.1); None = voice off
        self.root = root if root is not None else tk.Tk()
        self.root.title("HERCULE AI Operating System")
        self.root.configure(bg=BG)
        self.root.geometry("1280x800")
        self.results: "queue.Queue[dict]" = queue.Queue()
        self._pulse_phase = 0
        self._build()
        self._poll()

    # --------------------------------------------------
    def _style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=PANEL, foreground=TEXT,
                        font=("Consolas", 10))
        style.configure("Header.TLabel", background=BG, foreground=ACCENT,
                        font=("Consolas", 16, "bold"))
        style.configure("Title.TLabel", background=PANEL, foreground=ACCENT,
                        font=("Consolas", 11, "bold"))
        style.configure("TButton", background="#1a2230", foreground=TEXT,
                        font=("Consolas", 10))
        style.configure("TEntry", fieldbackground="#1a2230", foreground=TEXT)

    def _panel(self, parent, title, row, column, rowspan=1, sticky="nsew"):
        frame = ttk.Frame(parent, style="Panel.TFrame", padding=8)
        frame.grid(row=row, column=column, rowspan=rowspan, sticky=sticky,
                   padx=6, pady=6)
        ttk.Label(frame, text=title, style="Title.TLabel").pack(anchor="w")
        return frame

    def _build(self):
        self._style()
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=8)
        header.grid(row=0, column=0, columnspan=3, sticky="ew")
        header.configure(style="TFrame")
        ttk.Label(header, text="HERCULE  //  AI OPERATING SYSTEM",
                  style="Header.TLabel").pack(side="left")
        self.state_var = tk.StringVar(value="UNKNOWN")
        self.state_label = tk.Label(header, textvariable=self.state_var,
                                    bg=BG, fg=DIM, font=("Consolas", 14, "bold"))
        self.state_label.pack(side="right")

        left = ttk.Frame(self.root)
        left.grid(row=1, column=0, sticky="nsew")
        center = ttk.Frame(self.root)
        center.grid(row=1, column=1, sticky="nsew")
        right = ttk.Frame(self.root)
        right.grid(row=1, column=2, sticky="nsew")
        right.configure(width=380)

        # Consciousness panel + arc visualization.
        conscious = self._panel(left, "CONSCIOUSNESS", 0, 0)
        self.arc = tk.Canvas(conscious, width=150, height=150,
                             bg=PANEL, highlightthickness=0)
        self.arc.pack()
        self.focus_var = tk.StringVar(value="focus: UNKNOWN")
        ttk.Label(conscious, textvariable=self.focus_var,
                  wraplength=220).pack(anchor="w")
        self.goal_var = tk.StringVar(value="goal: UNKNOWN")
        ttk.Label(conscious, textvariable=self.goal_var,
                  wraplength=220).pack(anchor="w")

        # Model panel.
        model = self._panel(left, "MODEL", 1, 0)
        self.model_var = tk.StringVar(value="model: UNKNOWN")
        ttk.Label(model, textvariable=self.model_var,
                  wraplength=220).pack(anchor="w")

        # Task panel + controls.
        task = self._panel(left, "TASK", 2, 0)
        self.task_var = tk.StringVar(value="task: none")
        ttk.Label(task, textvariable=self.task_var,
                  wraplength=220).pack(anchor="w")
        controls = ttk.Frame(task, style="Panel.TFrame")
        controls.pack(fill="x", pady=(6, 0))
        for label, action in (("Pause", "pause"), ("Resume", "resume"),
                              ("Cancel", "cancel")):
            ttk.Button(controls, text=label,
                       command=lambda a=action: self._control(a)).pack(
                           side="left", expand=True, fill="x", padx=2)

        # Autonomy panel (small; live worker status + controls).
        autonomy = self._panel(left, "AUTONOMY", 3, 0)
        self.autonomy_var = tk.StringVar(value="autonomy: UNKNOWN")
        ttk.Label(autonomy, textvariable=self.autonomy_var,
                  wraplength=220).pack(anchor="w")
        autonomy_controls = ttk.Frame(autonomy, style="Panel.TFrame")
        autonomy_controls.pack(fill="x", pady=(6, 0))
        for label, action in (("Start", "autonomy_start"),
                              ("Stop", "autonomy_stop"),
                              ("Hold", "autonomy_pause"),
                              ("Go", "autonomy_resume")):
            ttk.Button(autonomy_controls, text=label,
                       command=lambda a=action: self._control(a)).pack(
                           side="left", expand=True, fill="x", padx=2)

        # Evaluation panel (v1.1; read-only, mirrors evaluation snapshots).
        evaluation = self._panel(left, "EVALUATION", 4, 0)
        self.evaluation_var = tk.StringVar(value="evaluation: idle")
        ttk.Label(evaluation, textvariable=self.evaluation_var,
                  wraplength=220).pack(anchor="w")

        # Voice panel (v1.1; opt-in interface layer, never blocks the UI).
        voice = self._panel(left, "VOICE", 5, 0)
        self.voice_var = tk.StringVar(value="voice: OFF")
        ttk.Label(voice, textvariable=self.voice_var,
                  wraplength=220).pack(anchor="w")
        self.voice_text_var = tk.StringVar(value="say: -")
        ttk.Label(voice, textvariable=self.voice_text_var,
                  wraplength=220).pack(anchor="w")
        voice_controls = ttk.Frame(voice, style="Panel.TFrame")
        voice_controls.pack(fill="x", pady=(6, 0))
        for label, action in (("On", "voice_enable"),
                              ("Listen", "voice_listen"),
                              ("Stop", "voice_stop"),
                              ("Mute", "voice_mute")):
            ttk.Button(voice_controls, text=label,
                       command=lambda a=action: self._voice_control(a)).pack(
                           side="left", expand=True, fill="x", padx=2)

        # Vision panel (v1.1; explicit read-only analysis, never continuous).
        vision = self._panel(left, "VISION", 6, 0)
        self.vision_var = tk.StringVar(value="vision: UNKNOWN")
        ttk.Label(vision, textvariable=self.vision_var,
                  wraplength=220).pack(anchor="w")
        self.vision_text_var = tk.StringVar(value="see: -")
        ttk.Label(vision, textvariable=self.vision_text_var,
                  wraplength=220).pack(anchor="w")
        vision_controls = ttk.Frame(vision, style="Panel.TFrame")
        vision_controls.pack(fill="x", pady=(6, 0))
        for label, action in (("Screen", "vision_screen"),
                              ("File", "vision_file")):
            ttk.Button(vision_controls, text=label,
                       command=lambda a=action: self._vision_control(a)).pack(
                           side="left", expand=True, fill="x", padx=2)

        # Computer panel (v1.2; explicit controlled interaction only).
        computer = self._panel(left, "COMPUTER USE", 7, 0)
        self.computer_var = tk.StringVar(value="computer: OFF")
        ttk.Label(computer, textvariable=self.computer_var,
                  wraplength=220).pack(anchor="w")
        self.computer_text_var = tk.StringVar(value="action: -")
        ttk.Label(computer, textvariable=self.computer_text_var,
                  wraplength=220).pack(anchor="w")
        computer_controls = ttk.Frame(computer, style="Panel.TFrame")
        computer_controls.pack(fill="x", pady=(6, 0))
        for label, action in (("Approve", "computer_approve"),
                              ("Reject", "computer_reject"),
                              ("Stop", "computer_stop")):
            ttk.Button(computer_controls, text=label,
                       command=lambda a=action: self._computer_control(a)).pack(
                           side="left", expand=True, fill="x", padx=2)

        # World panel (v2; read-only context summary, never the database).
        world = self._panel(left, "WORLD", 8, 0)
        self.world_var = tk.StringVar(value="world: UNKNOWN")
        ttk.Label(world, textvariable=self.world_var,
                  wraplength=220).pack(anchor="w")
        self.world_text_var = tk.StringVar(value="entities: -")
        ttk.Label(world, textvariable=self.world_text_var,
                  wraplength=220).pack(anchor="w")

        # Memory panel (v2; read-only summary, never private reasoning).
        mempanel = self._panel(left, "MEMORY", 9, 0)
        self.memory_var = tk.StringVar(value="memory: UNKNOWN")
        ttk.Label(mempanel, textvariable=self.memory_var,
                  wraplength=220).pack(anchor="w")
        self.memory_text_var = tk.StringVar(value="recall: -")
        ttk.Label(mempanel, textvariable=self.memory_text_var,
                  wraplength=220).pack(anchor="w")

        # Reasoning panel (v2 Phase 4; decision readout, never CoT).
        reasonpanel = self._panel(left, "REASONING", 10, 0)
        self.reasoning_var = tk.StringVar(value="reasoning: UNKNOWN")
        ttk.Label(reasonpanel, textvariable=self.reasoning_var,
                  wraplength=220).pack(anchor="w")
        self.reasoning_text_var = tk.StringVar(value="model: -")
        ttk.Label(reasonpanel, textvariable=self.reasoning_text_var,
                  wraplength=220).pack(anchor="w")

        # Decision panel (v2 Phase 5; read-only strategy readout, never CoT).
        decisionpanel = self._panel(left, "DECISION", 11, 0)
        self.decision_var = tk.StringVar(value="decision: idle")
        ttk.Label(decisionpanel, textvariable=self.decision_var,
                  wraplength=220).pack(anchor="w")
        self.decision_text_var = tk.StringVar(value="reason: -")
        ttk.Label(decisionpanel, textvariable=self.decision_text_var,
                  wraplength=220).pack(anchor="w")

        # Plugins panel (Plugin Platform)
        if PLUGIN_PANEL_AVAILABLE:
            self.plugins_panel = PluginPanel(left, self.controller)
            self.plugins_panel.frame.grid(row=12, column=0, sticky="nsew", padx=6, pady=6)
            left.rowconfigure(12, weight=1)

        # Event stream.
        stream = self._panel(center, "EVENT STREAM", 0, 0)
        self.events = scrolledtext.ScrolledText(
            stream, bg="#0d1219", fg=TEXT, font=("Consolas", 9),
            height=30, state="disabled", wrap="word")
        self.events.pack(expand=True, fill="both")
        self._seen_events = 0

        # Conversation panel.
        conv = self._panel(right, "CONSOLE", 0, 0)
        self.chat = scrolledtext.ScrolledText(
            conv, bg="#0d1219", fg=TEXT, font=("Consolas", 10),
            height=28, state="disabled", wrap="word")
        self.chat.pack(expand=True, fill="both")
        entry_row = ttk.Frame(conv, style="Panel.TFrame")
        entry_row.pack(fill="x", pady=(6, 0))
        self.entry = ttk.Entry(entry_row)
        self.entry.pack(side="left", expand=True, fill="x")
        self.entry.bind("<Return>", lambda _e: self._send())
        self.send_btn = ttk.Button(entry_row, text="Send", command=self._send)
        self.send_btn.pack(side="right", padx=(6, 0))
        self._append_chat("HERCULE interface online. Type hi, calculate 25+4, ...")

    # --------------------------------------------------
    # Actions (worker thread; UI never blocks on the model)
    # --------------------------------------------------
    def _send(self):
        text = self.entry.get().strip()
        if not text or self.controller.busy:
            return
        self.entry.delete(0, "end")
        self.send_btn.state(["disabled"])
        self._append_chat(f"> {text}")
        threading.Thread(target=self._worker_submit, args=(text,),
                         daemon=True).start()

    def _worker_submit(self, text):
        try:
            result = self.controller.submit(text)
            self.results.put({"ok": True, "result": result})
        except Exception as exc:  # never crash the worker silently
            self.results.put({"ok": False, "error": str(exc)[:300]})

    def _control(self, action):
        try:
            if action == "pause":
                outcome = self.controller.pause_current()
            elif action == "resume":
                outcome = self.controller.resume_current()
            elif action == "autonomy_start":
                outcome = self.controller.start_autonomy()
            elif action == "autonomy_stop":
                outcome = self.controller.stop_autonomy()
            elif action == "autonomy_pause":
                outcome = self.controller.pause_autonomy()
            elif action == "autonomy_resume":
                outcome = self.controller.resume_autonomy()
            else:
                outcome = self.controller.cancel_current()
            self._append_chat(f"[{action}] {outcome}")
        except Exception as exc:
            self._append_chat(f"[{action} failed] {exc}")
        self._refresh()

    def _voice_control(self, action):
        """Voice panel actions (non-blocking; worker threads do the work)."""
        if self.voice is None:
            self._append_chat("[voice] voice subsystem not attached (v1.1 interface)")
            return
        try:
            if action == "voice_enable":
                snap = self.voice.snapshot()
                outcome = self.voice.disable() if snap.get("enabled") else self.voice.enable()
            elif action == "voice_listen":
                outcome = self.voice.listen_once()
            elif action == "voice_mute":
                snap = self.voice.snapshot()
                outcome = self.voice.set_muted(not snap.get("muted", False))
            else:
                outcome = self.voice.stop()
            self._append_chat(f"[{action}] {outcome}")
        except Exception as exc:
            self._append_chat(f"[{action} failed] {exc}")
        self._refresh()

    def _vision_control(self, action):
        """Vision panel actions (explicit only; worker thread, never blocks)."""
        if action == "vision_screen":
            threading.Thread(target=self._worker_vision_screen,
                             daemon=True).start()
        else:
            self._append_chat("[vision] type: analyze image <workspace-path> "
                              "(or screenshot) in the console")

    def _worker_vision_screen(self):
        try:
            result = self.controller.submit("Analyze this screen (screenshot)")
            text = self.controller.format_response(result)
        except Exception as exc:
            text = f"[vision failed] {exc}"
        self.results.put({"ok": True, "result": {"kind": "QUESTION",
                                                 "status": "answered",
                                                 "response": text}})

    def _computer_control(self, action):
        """Computer panel actions: approvals + stop (never executes)."""
        try:
            if action == "computer_stop":
                outcome = self.controller.computer_cancel()
            else:
                snap = self.controller.computer_snapshot()
                pending = (snap or {}).get("pending_approvals") or []
                if not pending:
                    self._append_chat("[computer] no pending approval request")
                    return
                request_id = pending[0].get("request_id", "")
                if action == "computer_approve":
                    outcome = self.controller.computer_approve(request_id)
                else:
                    outcome = self.controller.computer_reject(request_id)
            self._append_chat(f"[{action}] {outcome}")
        except Exception as exc:
            self._append_chat(f"[{action} failed] {exc}")
        self._refresh()

    # --------------------------------------------------
    # Poll loop: drain results, refresh panels, animate
    # --------------------------------------------------
    def _poll(self):
        try:
            while True:
                message = self.results.get_nowait()
                self._on_result(message)
        except queue.Empty:
            pass
        self._refresh()
        self._animate()
        self.root.after(500, self._poll)

    def _on_result(self, message):
        self.send_btn.state(["!disabled"])
        if not message.get("ok"):
            self._append_chat(f"[HERCULE Error] {message.get('error', 'unknown error')}")
            return
        text = self.controller.format_response(message["result"])
        self._append_chat(text or "(empty response)")

    def _append_chat(self, text):
        self.chat.configure(state="normal")
        self.chat.insert("end", str(text).strip() + "\n")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _append_events(self, events):
        if not events:
            return
        self.events.configure(state="normal")
        for event in events:
            self.events.insert("end",
                               f"{event.get('stage', '?'):16.16s} "
                               f"{event.get('summary', '')[:110]}\n")
        self.events.see("end")
        self.events.configure(state="disabled")

    def _refresh(self):
        try:
            snap = self.controller.snapshot()
        except Exception:
            return
        state = ((snap.get("consciousness") or {}).get("state") or "UNKNOWN")
        self.state_var.set(state)
        self.state_label.configure(fg=STATE_COLORS.get(state, DIM))
        focus = ((snap.get("consciousness") or {}).get("focus") or "UNKNOWN")
        self.focus_var.set(f"focus: {focus[:120]}")
        goals = snap.get("goals") or {}
        active = goals.get("active") or []
        if active:
            first = active[0]
            self.goal_var.set(f"goal [{first.get('status', '?')}]: {first.get('goal', '')[:120]}")
        else:
            self.goal_var.set("goal: none")
        model = snap.get("model") or {}
        availability = "online" if model.get("available") else "UNAVAILABLE"
        self.model_var.set(
            f"provider: {model.get('provider', 'UNKNOWN')}\n"
            f"model: {model.get('model', 'UNKNOWN')}\n"
            f"runtime: {model.get('runtime', 'UNKNOWN')}\n"
            f"device: {model.get('device', 'UNKNOWN')}\n"
            f"status: {availability}\n"
            f"load: {model.get('load_time_s', 'UNKNOWN')}\n"
            f"speed: {model.get('tokens_per_sec', 'UNKNOWN')}\n"
            f"probe: {model.get('health_probe_latency_ms', 'UNKNOWN')} ms")
        task = snap.get("task") or {}
        if task.get("id"):
            lines = [f"id: {task.get('id')}", f"goal: {task.get('goal', '')[:100]}",
                     f"status: {task.get('status')}", f"progress: {task.get('progress')}",
                     f"verification: {task.get('verification')}"]
            for step in (task.get("steps") or [])[:8]:
                mark = "[x]" if step.get("status", "").lower() == "completed" else (
                    ">" if step.get("status", "").lower() in ("running", "executing") else "-")
                lines.append(f"  {mark} {step.get('id')} -> {step.get('status')}"
                             + (" [verified]" if step.get("verified") else ""))
            self.task_var.set("\n".join(lines))
        else:
            self.task_var.set("task: none")
        autonomy = snap.get("autonomy") or {}
        try:
            last = autonomy.get("last_result") or {}
            self.autonomy_var.set(
                f"enabled: {autonomy.get('enabled', 'UNKNOWN')}\n"
                f"worker: {autonomy.get('worker_state', 'UNKNOWN')}\n"
                f"queued: {list(autonomy.get('queued', []) or [])}\n"
                f"active: {autonomy.get('active_task', '') or 'none'}\n"
                f"last: {last.get('task_id', '')} {last.get('status', '')} "
                f"{str(last.get('summary', ''))[:60]}".strip())
        except Exception:
            self.autonomy_var.set("autonomy: UNKNOWN")
        # Voice/HUD indicators (v1.1): real voice-controller state only.
        try:
            if self.voice is None:
                self.voice_var.set("voice: OFF (not attached)")
                self.voice_text_var.set("say: -")
            else:
                vsnap = self.voice.snapshot()
                mic = "ON" if vsnap.get("mic_on") else "OFF"
                self.voice_var.set(
                    f"voice: {'ON' if vsnap.get('enabled') else 'OFF'}  "
                    f"mic: {mic}  {vsnap.get('state', 'IDLE')}"
                    + (" [MUTED]" if vsnap.get("muted") else "")
                    + (" [SPEAKING]" if vsnap.get("speaking") else "")
                    + (" [LISTENING]" if vsnap.get("listening") else ""))
                said = vsnap.get("last_transcript", "") or "-"
                self.voice_text_var.set(f"say: {said[:90]}")
        except Exception:
            self.voice_var.set("voice: UNKNOWN")
        # Vision/HUD indicators (v1.1): real snapshot state only.
        try:
            vsnap = (snap.get("vision") or {})
            state = str(vsnap.get("state", "UNKNOWN"))
            if not vsnap.get("available", True) and state == "UNKNOWN":
                state = "UNAVAILABLE"
            self.vision_var.set(f"vision: {state}")
            seen = str(vsnap.get("description", "") or "-")[:90]
            self.vision_text_var.set(f"see: {seen}")
        except Exception:
            try:
                self.vision_var.set("vision: UNKNOWN")
            except Exception:
                pass
        # Computer/HUD indicators (v1.2): real controller state only.
        try:
            csnap = (snap.get("computer") or {})
            cstate = str(csnap.get("state", "UNKNOWN"))
            enabled = "ON" if csnap.get("enabled") else "OFF"
            self.computer_var.set(f"computer: {enabled} {cstate}")
            pending = csnap.get("pending_approvals") or []
            if pending:
                first = pending[0] or {}
                self.computer_text_var.set(
                    f"HERCULE ACTION REQUEST {first.get('app', '')} "
                    f"{first.get('action', {}).get('action', '')} "
                    f"[{first.get('risk', '')}] approve?")
            else:
                proposed = str(csnap.get("proposed_action", "") or "-")[:60]
                self.computer_text_var.set(
                    f"action: {proposed} verified={csnap.get('verified', False)}")
        except Exception:
            try:
                self.computer_var.set("computer: UNKNOWN")
            except Exception:
                pass
        # World/HUD indicators (v2): real repository state only.
        # UPDATING is shown while the controller is busy (observations
        # may be landing); otherwise SYNCED/DEGRADED from the store.
        try:
            wsnap = (snap.get("world") or {})
            wstate = str(wsnap.get("state", "UNKNOWN"))
            if snap.get("busy") and wstate == "SYNCED":
                wstate = "UPDATING"
            self.world_var.set(f"world: {wstate}")
            apps = ", ".join((wsnap.get("applications") or [])[:3]) or "-"
            self.world_text_var.set(
                f"entities: {wsnap.get('entities', 0)} apps: {apps}")
        except Exception:
            try:
                self.world_var.set("world: UNKNOWN")
            except Exception:
                pass
        # Memory/HUD indicators (v2): real store state only.
        try:
            msnap = (snap.get("memory") or {})
            mstate = str(msnap.get("state", "UNKNOWN"))
            self.memory_var.set(f"memory: {mstate}")
            recall = msnap.get("recall") or {}
            if recall.get("recent"):
                self.memory_text_var.set(
                    f"recall: {recall.get('count', 0)} hits")
            else:
                recent = msnap.get("recent") or []
                first = str((recent[0] or {}).get("content", ""))[:60] \
                    if recent else "-"
                self.memory_text_var.set(f"recent: {first}")
        except Exception:
            try:
                self.memory_var.set("memory: UNKNOWN")
            except Exception:
                pass
        # Reasoning/HUD indicators (v2 Phase 4): real decision values.
        try:
            rsnap = (snap.get("reasoning") or {})
            rmode = str(rsnap.get("mode", "UNKNOWN"))
            self.reasoning_var.set(f"reasoning: {rmode}")
            model = str(rsnap.get("model", "") or "-")[:40]
            latency = rsnap.get("latency_ms", 0.0) or 0.0
            self.reasoning_text_var.set(
                f"model: {model} {rsnap.get('budget_summary', '')} "
                f"{latency}ms".strip())
        except Exception:
            try:
                self.reasoning_var.set("reasoning: UNKNOWN")
            except Exception:
                pass
        # Decision/HUD indicators (v2 Phase 5): real decision-record values.
        try:
            dsnap = (snap.get("decision") or {})
            if dsnap.get("available"):
                self.decision_var.set(
                    f"candidates: {dsnap.get('candidates', 0)}"
                    f"\nselected: {dsnap.get('selected', '-') or '-'}"
                    f"\nmode: {dsnap.get('selected_mode', '-') or '-'}"
                    f"\n{dsnap.get('decision_time_ms', 0.0)} ms")
                self.decision_text_var.set(
                    f"reason: {str(dsnap.get('reason', '') or '-')[:150]}")
            else:
                self.decision_var.set("decision: idle")
                self.decision_text_var.set("reason: -")
        except Exception:
            try:
                self.decision_var.set("decision: UNKNOWN")
            except Exception:
                pass
        # Evaluation HUD (v1.1): read-only progress from the runner state.
        try:
            evaluation = snap.get("evaluation") or {}
            if evaluation.get("available"):
                if evaluation.get("running"):
                    self.evaluation_var.set(
                        f"suite: {evaluation.get('suite', 'UNKNOWN')}"
                        f"\ntask: {evaluation.get('done', 0)}/{evaluation.get('total', '?')}"
                        f"\npass: {evaluation.get('passed', 0)}  "
                        f"fail: {evaluation.get('failed', 0)}"
                        f"\nscore: {evaluation.get('score', 'n/a')}"
                        f"\nmodel: {evaluation.get('model', 'UNKNOWN')}"
                        f"\nelapsed: {evaluation.get('elapsed_s', 0)}s")
                else:
                    self.evaluation_var.set(
                        f"last: {evaluation.get('mode', '?')} "
                        f"pass {evaluation.get('passed', 0)} "
                        f"fail {evaluation.get('failed', 0)}")
            else:
                self.evaluation_var.set("evaluation: idle")
        except Exception:
            self.evaluation_var.set("evaluation: UNKNOWN")
        events = snap.get("events") or []
        fresh = events[self._seen_events:] if len(events) >= self._seen_events else events
        self._seen_events = len(events)
        self._append_events(fresh)
        if snap.get("busy"):
            self.send_btn.state(["disabled"])
        elif not self.controller.busy:
            self.send_btn.state(["!disabled"])

    def _animate(self):
        # Subtle arc pulse keyed off the live state color (decoration only;
        # all data on screen comes from runtime snapshots).
        try:
            state = self.state_var.get()
            color = STATE_COLORS.get(state, DIM)
            self._pulse_phase = (self._pulse_phase + 12) % 360
            self.arc.delete("all")
            self.arc.create_oval(15, 15, 135, 135, outline="#1a2230", width=8)
            self.arc.create_arc(15, 15, 135, 135, start=self._pulse_phase,
                                extent=120, outline=color, width=8, style="arc")
            self.arc.create_text(75, 75, text=state[:8], fill=color,
                                 font=("Consolas", 10, "bold"))
        except Exception:
            pass

    def run(self):
        self.root.mainloop()


def launch(controller, voice=None):
    """Build and run the desktop app for a live controller."""
    try:
        import tkinter as tk  # noqa: F401 (display probe)
    except Exception as exc:
        raise RuntimeError(f"desktop UI unavailable (tkinter missing): {exc}")
    if voice is None:
        # Voice is an opt-in interface layer (v1.1, disabled by default);
        # attach it so the VOICE panel is available in every launcher.
        try:
            from voice.controller import VoiceController
            voice = VoiceController(controller)
        except Exception:
            voice = None
    try:
        app = HerculeDesktopApp(controller, voice=voice)
    except Exception as exc:
        raise RuntimeError(f"desktop UI unavailable (no display?): {exc}")
    app.run()
    return app
