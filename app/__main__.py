"""入口：默认桌面窗口模式；server 子命令为无界面模式。"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="panhub", description="盘枢 Knowledge Base Engine")
    parser.add_argument("cmd", nargs="?", default="desktop", choices=["desktop", "server"],
                        help="desktop=本地窗口（默认）；server=无界面后端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7869)
    parser.add_argument("--debug", action="store_true", help="打开 WebView 调试模式")
    args = parser.parse_args()

    if args.cmd == "desktop":
        from app.desktop import main as desktop_main

        return desktop_main(debug=args.debug)

    import uvicorn

    from app.main import create_app

    print(f"LISTENING port={args.port}", flush=True)
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
