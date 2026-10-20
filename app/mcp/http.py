"""MCP Streamable HTTP 服务：独立 loopback 端口，供本地 Agent 连接。"""

from __future__ import annotations

import socket
import threading
import time

import uvicorn

from app.mcp.server import mcp_server


def _port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True
        except OSError:
            return False


def pick_mcp_port(preferred: int, host: str = "127.0.0.1") -> int:
    for p in range(preferred, preferred + 10):
        if _port_free(p, host):
            return p
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def _wait_listen(port: int, host: str = "127.0.0.1", timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.3)
            try:
                s.connect((host, port))
                return True
            except OSError:
                time.sleep(0.1)
    return False


def start_mcp_http(preferred_port: int = 7868, host: str = "127.0.0.1"):
    """启动 Streamable HTTP MCP 服务，返回 (server, thread, port)。"""
    port = pick_mcp_port(preferred_port, host)
    # 无状态模式：每个请求独立处理，Agent 无需维护会话，进程退出不等待空闲会话
    mcp_app = mcp_server.streamable_http_app(host=host, stateless_http=True, json_response=True)
    config = uvicorn.Config(
        mcp_app, host=host, port=port, log_level="warning", log_config=None, lifespan="on"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="panhub-mcp-http")
    thread.start()
    if not _wait_listen(port, host):
        server.should_exit = True
        raise RuntimeError(f"MCP 端口 {port} 启动超时")
    return server, thread, port


def stop_mcp_http(server: uvicorn.Server | None, thread: threading.Thread | None) -> None:
    if server is not None:
        server.should_exit = True
    if thread is not None:
        thread.join(timeout=5)