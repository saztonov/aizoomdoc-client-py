# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for AIZoomDoc Client

Сборка:
    pip install pyinstaller
    pyinstaller aizoomdoc.spec

Результат будет в dist/AIZoomDoc.exe
"""

block_cipher = None

a = Analysis(
    ['run_gui.py'],
    pathex=['src'],
    binaries=[],
    datas=[],
    hiddenimports=[
        # HTTP клиент
        'httpx',
        'httpx._transports',
        'httpx._transports.default',
        'httpx_sse',
        'httpx_sse._decoders',
        'httpx_sse._exceptions',
        'anyio',
        'anyio._backends',
        'anyio._backends._asyncio',
        'sniffio',
        'h11',
        'h2',
        'hpack',
        'hyperframe',
        'certifi',
        'idna',
        'socksio',

        # PyQt6 GUI
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtWidgets',
        'PyQt6.QtGui',
        'PyQt6.QtNetwork',
        'PyQt6.sip',

        # Pydantic
        'pydantic',
        'pydantic.deprecated',
        'pydantic.deprecated.decorator',
        'pydantic_core',
        'annotated_types',

        # CLI (может понадобиться)
        'click',
        'rich',
        'rich.console',
        'rich.table',
        'rich.panel',
        'rich.markdown',
        'rich.syntax',
        'rich.progress',

        # Стандартные библиотеки
        'json',
        'logging',
        'datetime',
        'pathlib',
        'uuid',
        'typing',
        'asyncio',
        'codecs',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Исключаем ненужные модули для уменьшения размера
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'PIL',
        'cv2',
        'tensorflow',
        'torch',
        'pytest',
        'unittest',
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
    name='AIZoomDoc',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI приложение - без консоли
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',  # Раскомментировать если добавите иконку
)
