"""入口：默认桌面窗口模式；server 为无界面后端；mcp 为 stdio 协议服务。"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="panhub", description="盘枢 Knowledge Base Engine")
    parser.add_argument(
        "cmd",
        nargs="?",
        default="desktop",
        choices=["desktop", "server", "mcp"],
        help="desktop=本地窗口（默认）；server=无界面后端；mcp=stdio MCP 服务",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7869)
    parser.add_argument("--mcp-port", type=int, default=7868, help="MCP HTTP 端口，0 表示关闭")
    parser.add_argument("--debug", action="store_true", help="打开 WebView 调试模式")
    args = parser.parse_args()

    if args.cmd == "desktop":
        from app.desktop import main as desktop_main

        return desktop_main(debug=args.debug, mcp_port=args.mcp_port)

    if args.cmd == "mcp":
        from app.mcp.server import mcp_server

        mcp_server.run(transport="stdio")
        return 0

    import uvicorn

    from app.main import create_app

    if args.mcp_port > 0:
        try:
            from app.mcp.http import start_mcp_http

            _, _, actual_port = start_mcp_http(args.mcp_port, args.host)
            print(f"MCP LISTENING port={actual_port}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"MCP disabled: {exc}", flush=True)

    print(f"LISTENING port={args.port}", flush=True)
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
