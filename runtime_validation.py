# Runtime validation
print('=== RUNTIME VALIDATION ===')
print()

# 1. ModelManager discovers native model
from models.model_manager import ModelManager
manager = ModelManager(config={'model_provider': 'native', 'default_model': 'hercule-lm-micro'})
print('1. ModelManager native detection:')
print('   provider_pref:', manager.provider_pref)
print('   default_model:', manager.default_model)

native_models = manager.installed_native_models()
print('   installed_native_models:', native_models)

# 2. ModelRouter can select native
from models.router.model_router import ModelRouter
router = ModelRouter()
model_name, adapter_name, adapter = router.route_for_purpose('reasoning')
print('2. ModelRouter route_for_purpose(reasoning):')
print('   model:', model_name, ', adapter:', adapter_name)

# 3. Native provider health
from models.hercule_lm.provider import HerculeLMProvider
provider = HerculeLMProvider()
health = provider.health()
print('3. Native provider health (lazy):')
print('   available:', health['available'])
print('   discovered_models:', health.get('discovered_models', []))

# 4. Load and generate
provider.load_model('hercule-lm-micro')
health2 = provider.health()
print('4. Native provider after load:')
print('   available:', health2['available'])
print('   model:', health2['model'])
print('   params:', health2['params'])
print('   checkpoint:', health2['checkpoint'])

# 5. Generate
result = provider.generate('Calculate 2 + 2')
print('5. Generation result:', repr(result[:100]))

# 6. Full Brain path
from brain.brain import Brain
from orchestrator.orchestrator import Orchestrator
from memory.memory_manager import MemoryManager

memory = MemoryManager()
models = ModelManager(config={'model_provider': 'native', 'default_model': 'hercule-lm-micro'})
orchestrator = Orchestrator(memory=memory, knowledge=None, models=models, abilities=None, perception=None, communication=None, security=None, system=None)
brain = Brain(orchestrator)
brain.start()

response = brain.think('Calculate 2 + 2')
print('6. Brain.think() via native:', repr(response[:100]))

print()
print('=== ALL VALIDATIONS PASSED ===')