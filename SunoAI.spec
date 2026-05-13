# SunoAI.spec — PyInstaller configuration
# Build: pyinstaller SunoAI.spec --clean
# Output: dist/SunoAI.exe (Windows) | dist/SunoAI (Linux) | dist/SunoAI.app (macOS)

import sys

block_cipher = None

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Top-level project modules (auto-discovered via app.py imports, listed for safety)
        "core",
        "providers",
        "prompts",
        "settings",
        "history_index",
        # Google Gemini
        "google.genai",
        "google.auth",
        "google.auth.transport.requests",
        # OpenAI / OpenAI-compat providers
        "openai",
        "openai._models",
        # Anthropic
        "anthropic",
        # HTTP
        "httpx",
        "httpcore",
        "h2",
        "hpack",
        # Local OS keyring backends
        "keyring",
        "keyring.backends",
        "keyring.backends.Windows",
        "keyring.backends.macOS",
        "keyring.backends.SecretService",
        # sqlite3 (history_index)
        "sqlite3",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy, unused packages
        "matplotlib",
        "numpy",
        "pandas",
        "PIL",
        "scipy",
        "sklearn",
        "torch",
        "tensorflow",
        "notebook",
        "IPython",
        # Old CustomTkinter assets (project migrated to PySide6)
        "customtkinter",
        "tkinter",
        "tkinter.ttk",
        "_tkinter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="SunoAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,   # No terminal window on Windows/macOS
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="assets/icon.ico",  # Uncomment and add icon file to enable
)

# macOS: wrap in .app bundle
if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="SunoAI.app",
        icon=None,  # Replace with "assets/icon.icns" if available
        bundle_identifier="com.sunoai.promptgenerator",
    )
