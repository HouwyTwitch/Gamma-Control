# gamma.spec
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['src/gamma.py'],
    pathex=[],
    binaries=[],
    datas=[('config.ini', '.')],
    hiddenimports=['PyQt5.QtWidgets', 'PyQt5.QtCore', 'PyQt5.QtGui', 'keyboard'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Unused PyQt5 modules (biggest size savings)
        'PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineCore',
        'PyQt5.QtNetwork', 'PyQt5.QtSql', 'PyQt5.QtXml', 'PyQt5.QtXmlPatterns',
        'PyQt5.QtBluetooth', 'PyQt5.QtNfc', 'PyQt5.QtSerialPort',
        'PyQt5.QtMultimedia', 'PyQt5.QtMultimediaWidgets',
        'PyQt5.QtLocation', 'PyQt5.QtPositioning', 'PyQt5.QtSensors',
        'PyQt5.Qt3DCore', 'PyQt5.Qt3DRender', 'PyQt5.Qt3DInput',
        'PyQt5.Qt3DLogic', 'PyQt5.Qt3DAnimation', 'PyQt5.Qt3DExtras',
        'PyQt5.QtPrintSupport', 'PyQt5.QtOpenGL',
        'PyQt5.QtTest', 'PyQt5.QtDesigner', 'PyQt5.QtHelp',
        'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtQuickWidgets',
        'PyQt5.QtRemoteObjects', 'PyQt5.QtWebChannel', 'PyQt5.QtWebSockets',
        'PyQt5.QtSvg',
        # Unused stdlib
        'tkinter', '_tkinter',
        'unittest', 'pydoc', 'doctest',
        'email', 'html', 'http', 'urllib', 'xml',
        'asyncio', 'multiprocessing', 'concurrent',
        'sqlite3', 'ftplib', 'imaplib', 'smtplib', 'poplib',
        'telnetlib', 'xmlrpc', 'ssl',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# One-file mode: pass binaries/datas directly into EXE, no COLLECT
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='GammaControl',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=['vcruntime140.dll', 'ucrtbase.dll'],
    console=False,
    icon='assets/icon.ico',
)
