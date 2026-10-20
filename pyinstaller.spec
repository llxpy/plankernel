# -*- mode: python ; coding: utf-8 -*-
# 盘枢 KBEngine 单文件桌面 exe 打包（PyInstaller 6.x，Windows 目标机执行）
# 产物：dist/Panhub.exe —— 双击即启动本地窗口（pywebview + Edge WebView2）
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ("frontend/dist", "frontend/dist"),
    ("migrations", "migrations"),
]
datas += collect_data_files("webview")

hiddenimports = [
    "fastapi", "fastapi.middleware", "fastapi.middleware.cors",
    "uvicorn", "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
    "uvicorn.loops.asyncio", "uvicorn.protocols", "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets", "uvicorn.lifespan",
    "pydantic", "pydantic_core",
    "sqlite3",
    "jieba", "jieba.analyse", "jieba.posseg",
    "pypdf", "pdfplumber", "pymupdf", "docx", "docx2txt", "openpyxl",
    "cryptography.hazmat",
    "openai", "httpx", "anyio", "anyio._backends", "anyio._backends._asyncio",
    "multipart", "python_multipart",
    "webview", "webview.platforms.edgechromium", "webview.platforms.winforms",
    "clr_loader", "pythonnet",
    "starlette", "sse_starlette",
]
hiddenimports += collect_submodules("webview")
hiddenimports += collect_submodules("mcp", filter=lambda name: not name.startswith("mcp.cli"))

a = Analysis(
    ["app/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "notebook", "pytest"],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="Panhub",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon="resources/icon.ico" if __import__("os").path.exists("resources/icon.ico") else None,
)
