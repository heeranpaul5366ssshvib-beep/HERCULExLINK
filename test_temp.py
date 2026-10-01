from memory.enhanced_memory_manager import EnhancedMemoryManager
from memory.memory_manager import MemoryManager
mm = MemoryManager()
emm = EnhancedMemoryManager(mm)
result = emm.retrieve_rank_compact_inject("test query")
print("Success:", result.injection_tokens)