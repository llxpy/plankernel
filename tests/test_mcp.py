"""MCP 工具层测试：工作区打开/索引/检索/完整性 + HTTP 端点握手。"""
from __future__ import annotations

from pathlib import Path

import pytest

from app import deps
from app.mcp import server as mcp
from app.workspace import anchor as anchor_mod


@pytest.fixture()
def ws_root(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "运维记录.txt").write_text(
        "服务器频繁重启的根因定位为内存溢出，处理方案是扩容内存并更换电源模块。",
        encoding="utf-8",
    )
    anchor_mod.initialize(root, "MCP 测试工作区")
    yield root
    deps.registry.shutdown()


def test_mcp_tools_end_to_end(ws_root: Path):
    opened = mcp.open_workspace(str(ws_root))
    ws_id = opened["id"]
    assert opened["state"] == "normal"

    listed = mcp.list_workspaces()
    assert any(w["id"] == ws_id for w in listed)

    scan = mcp.scan_documents_tool(ws_id)
    assert scan["added"] == 1
    idx = mcp.index_documents_tool(ws_id)
    assert idx["indexed"] == 1 and idx["failed"] == 0

    docs = mcp.list_documents(ws_id)
    assert len(docs) == 1 and docs[0]["status"] == "ready"

    result = mcp.search(ws_id, "内存溢出 重启", use_pivot=False)
    assert result["results"], "MCP 检索应命中"
    assert result["results"][0]["rel_path"].endswith("运维记录.txt")
    assert "snippet" in result["results"][0]

    verified = mcp.verify_integrity(ws_id)
    assert verified["ok"] is True

    budget = mcp.get_budget(ws_id)
    assert "monthly" in budget


def test_mcp_http_initialize():
    from contextlib import AsyncExitStack

    import anyio
    from httpx import ASGITransport, AsyncClient

    app = mcp.mcp_server.streamable_http_app(host="127.0.0.1", stateless_http=True, json_response=True)

    async def handshake():
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(app.router.lifespan_context(app))
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
                return await client.post(
                    "/mcp",
                    headers={
                        "Accept": "application/json, text/event-stream",
                        "Content-Type": "application/json",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "pytest", "version": "0.0.0"},
                        },
                    },
                )

    resp = anyio.run(handshake)
    assert resp.status_code == 200
    assert "result" in resp.json()
