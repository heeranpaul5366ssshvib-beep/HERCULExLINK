"""
--------------------------------------------
HERCULE AI Operating System
Module: patch_imports.py
Author: Heeran Paul
License: MIT
--------------------------------------------
Automatically scans and patches import typos
to match exact filenames on disk.
"""

import os
import logging

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("HERCULE.Patcher")

# Map of incorrect/expected imports to actual file module names
IMPORT_FIXES = {
    # memory_manager.py fixes
    "from memory.vector.vector_memory import": "from memory.vector.vector_manager import",
    "from memory.retrieval.retrieval_engine import": "from memory.retrieval.retrival_engine import",
    # ability_manager.py fixes
    "from abilities.documents.document_ability import": "from abilities.documents.documents_ability import",
    # system_manager.py fixes
    "from system.diagnostics.diagnostics_manager import": "from system.diagnostics.diagonistics_manager import",
}

def patch_file(file_path: str):
    """Replace known incorrect import strings in a given python file."""
    if not os.path.exists(file_path):
        return
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    updated = False
    for wrong_import, correct_import in IMPORT_FIXES.items():
        if wrong_import in content:
            content = content.replace(wrong_import, correct_import)
            updated = True
            logger.info(f"Fixed import in {file_path}: {wrong_import} -> {correct_import}")
            
    if updated:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

def run_patcher():
    logger.info("Scanning project files for import discrepancies...")
    
    # Files known to contain manager imports
    target_files = [
        "memory/memory_manager.py",
        "abilities/ability_manager.py",
        "system/system_manager.py"
    ]
    
    for tf in target_files:
        patch_file(tf)
        
    # Also check all files in memory/, abilities/, system/ just in case
    for root, _, files in os.walk("."):
        for file in files:
            if file.endswith(".py") and file != "patch_imports.py":
                patch_file(os.path.join(root, file))

    logger.info("Import patching complete!")

if __name__ == "__main__":
    run_patcher()