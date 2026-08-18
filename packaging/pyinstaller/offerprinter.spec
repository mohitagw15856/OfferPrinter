# PyInstaller spec — builds a single-file `offerprinter` executable.
#
#   pip install pyinstaller
#   pyinstaller packaging/pyinstaller/offerprinter.spec --noconfirm --clean
#
# The result is one binary with no Python installation required, which is the
# whole point: most people who need a tailored CV are not going to set up a
# virtualenv first. The web UI is deliberately excluded — Streamlit does not
# bundle cleanly and the CLI is what benefits from being a single file.

import os

block_cipher = None

ENTRY = os.path.join("packaging", "pyinstaller", "entrypoint.py")

a = Analysis(
    [ENTRY],
    pathex=["."],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Providers are resolved through a registry, so PyInstaller's static
        # analysis cannot see them being imported.
        "offerprinter.llm.anthropic_provider",
        "offerprinter.llm.openai_provider",
        "offerprinter.llm.gemini_provider",
        "offerprinter.llm.kimi_provider",
        "offerprinter.llm.ollama_provider",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Streamlit is an optional extra; keep it out of the standalone CLI binary.
    excludes=["streamlit", "tkinter", "matplotlib", "numpy", "pandas", "IPython"],
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
    name="offerprinter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
