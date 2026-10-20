"""桌面模式：后台线程运行 FastAPI，pywebview 打开本地原生窗口（WebView2）。"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
from pathlib import Path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    d = Path(base) / "Panhub" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _log_exception(exc: BaseException) -> None:
    try:
        log = _app_data_dir() / "desktop.log"
        with log.open("a", encoding="utf-8") as f:
            import datetime

            f.write(f"\n[{datetime.datetime.now().isoformat(timespec='seconds')}] {exc}\n")
            traceback.print_exception(type(exc), exc, exc.__traceback__, file=f)
    except OSError:
        pass


def _message_box(text: str, title: str = "盘枢启动失败") -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)
    except (AttributeError, OSError):
        pass


def run_desktop(debug: bool = False) -> int:
    import uvicorn

    from app.deps import registry
    from app.main import create_app

    port = _free_port()
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="panhub-uvicorn")
    thread.start()

    deadline = time.time() + 20
    ready = False
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/v1/healthz", timeout=0.5):
                ready = True
                break
        except Exception:  # noqa: BLE001
            time.sleep(0.15)
    if not ready:
        raise RuntimeError("后端启动超时（20s）")

    import webview

    webview.create_window(
        "盘枢 · 知识库中台",
        f"http://127.0.0.1:{port}",
        width=1320,
        height=860,
        min_size=(980, 640),
        background_color="#f4f0e7",
        text_select=True,
    )
    webview.start(debug=debug)

    server.should_exit = True
    thread.join(timeout=5)
    registry.shutdown()
    return 0


def main(debug: bool = False) -> int:
    try:
        return run_desktop(debug=debug)
    except BaseException as exc:  # noqa: BLE001
        _log_exception(exc)
        _message_box(
            f"{exc}\n\n详细日志：{_app_data_dir() / 'desktop.log'}\n\n"
            "若提示缺少 WebView2 运行时，请安装 Microsoft Edge WebView2 Runtime 后重试。"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
