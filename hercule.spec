# HERCULE PyInstaller build (reproducible, --onedir).
# Build with:  python scripts/build_exe.py
# Output:      dist/HERCULE/HERCULE.exe  (+ bundled resources)
#
# --onedir is deliberate: faster startup and safer resource loading
# than --onefile. No tests, caches, venv, logs, or model weights
# are bundled. Ollama models are never packaged.
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hercule_hidden = []
for pkg in (
    "abilities", "agents", "autonomy", "boot", "brain", "cognition",
    "communication", "computer", "config", "engineering", "intelligence",
    "interface", "kernel", "knowledge", "memory", "models",
    "orchestrator", "perception", "plugin_sdk", "plugins",
    "profiles", "robotics", "runtime", "scripts", "security",
    "simulation", "system", "tools", "app", "voice", "world",
):
    try:
        hercule_hidden += collect_submodules(pkg)
    except Exception:
        pass

a = Analysis(
    ["app/main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("boot.py", "."),
        ("config/hercule.example.json", "config"),
        ("assets/hercule.ico", "assets"),
        ("assets/hercule.png", "assets"),
    ],
    hiddenimports=hercule_hidden + ["tkinter"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Heavy/broken ML stacks are excluded on purpose: every consumer
    # guards these imports (try/except -> available()=False) and HERCULE
    # degrades honestly (hash embeddings, Ollama path).torch's C
    # extension is unloadable in this environment, so bundling it would
    # only ship dead weight. No model weights are ever bundled.
    excludes=["tests", "pytest", "_pytest", "tkinter.test",
              "torch", "transformers", "sentence_transformers",
              "chromadb", "sklearn", "scipy"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HERCULE",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    icon="assets/hercule.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="HERCULE",
)
