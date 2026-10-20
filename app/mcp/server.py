"""盘枢 MCP 服务端：把工作区检索/索引/完整性能力暴露给本地 Agent。

工具列表（均返回 JSON 可序列化 dict）：
- list_workspaces / open_workspace / workspace_status
- list_documents / scan_documents / index_documents
- search / verify_integrity / get_budget
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from app.deps import registry
from app.index.service import delete_document, index_documents, scan_documents
from app.integrity.chain import ChainCorrupt
from app.llm.budget import Budget
from app.retrieval.engine import retrieve
from app.workspace import anchor as anchor_mod
from app.workspace.locking import WorkspaceLocked

mcp_server = MCPServer(
    name="panhub-kbengine",
    title="盘枢知识库中台",
    version="1.0.0",
    instructions=(
        "盘枢是本地目录级 RAG 知识库。使用流程：先 list_workspaces 查看已打开的工作区，"
        "或 open_workspace 打开一个目录；再用 search 做中文检索（返回切片、来源路径、融合分数），"
        "必要时 scan_documents + index_documents 建索引，verify_integrity 校验 Merkle 链。"
        "所有数据都在本机工作区目录内，不会上传云端。"
    ),
)


def _get_ws(workspace_id: str):
    try:
        return registry.get(workspace_id)
    except KeyError:
        raise ValueError(f"workspace.not_found: {workspace_id}") from None


def _ws_summary(ws) -> dict[str, Any]:
    return {
        "id": ws.workspace_id,
        "name": ws.cfg.name,
        "root_path": str(ws.root),
        "state": ws.state.state,
        "reason": ws.state.reason,
        "stats": ws.stats(),
    }


@mcp_server.tool(description="列出当前进程内已打开的工作区及其状态与统计。")
def list_workspaces() -> list[dict[str, Any]]:
    return [_ws_summary(ws) for ws in registry.list()]


@mcp_server.tool(description="打开（或初始化后打开）一个本地目录作为知识库工作区。root_path 为绝对路径。")
def open_workspace(root_path: str) -> dict[str, Any]:
    root = Path(root_path).expanduser()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"path.inaccessible: 目录不存在 {root}")
    hidden = root / ".kbengine"
    if not (hidden / "workspace.toml").exists():
        raise ValueError("workspace.not_found: 该目录尚未初始化，请先在盘枢窗口中初始化工作区")
    try:
        ws = registry.open(root)
    except anchor_mod.AnchorMismatch as e:
        raise ValueError(f"workspace.anchor_mismatch: {e}") from e
    except anchor_mod.WorkspaceNotInitialized as e:
        raise ValueError(f"workspace.not_found: {e}") from e
    except WorkspaceLocked as e:
        raise ValueError(f"workspace.locked: 已被其他进程占用（{e}）") from e
    return _ws_summary(ws)


@mcp_server.tool(description="查询工作区状态（normal / detached / tampered）、原因与文档/切片统计。")
def workspace_status(workspace_id: str) -> dict[str, Any]:
    return _ws_summary(_get_ws(workspace_id))


@mcp_server.tool(description="列出工作区内已登记的文档（最多 500 条），含状态与解析器信息。")
def list_documents(workspace_id: str) -> list[dict[str, Any]]:
    ws = _get_ws(workspace_id)
    conn = ws.db.connect()
    rows = conn.execute(
        "SELECT doc_id, rel_path, status, size_bytes, page_count, parser_version, error_msg "
        "FROM docs WHERE workspace_id=? ORDER BY rel_path LIMIT 500",
        (workspace_id,),
    ).fetchall()
    return [dict(r) for r in rows]


@mcp_server.tool(name="scan_documents", description="扫描工作区目录，登记新增/变更文档（不解析）。返回 added/updated 数量。")
def scan_documents_tool(workspace_id: str, force: bool = False) -> dict[str, Any]:
    ws = _get_ws(workspace_id)
    if not ws.state.can_write():
        raise ValueError(f"workspace.{ws.state.state}: 当前状态禁止写索引（{ws.state.reason}）")
    return scan_documents(ws, force=force)


@mcp_server.tool(name="index_documents", description="对 pending/failed 文档（或指定 doc_ids）执行解析、切块并写入 FTS5 索引。")
def index_documents_tool(workspace_id: str, doc_ids: list[int] | None = None) -> dict[str, Any]:
    ws = _get_ws(workspace_id)
    if not ws.state.can_write():
        raise ValueError(f"workspace.{ws.state.state}: 当前状态禁止写索引（{ws.state.reason}）")
    return index_documents(ws, doc_ids or None)


@mcp_server.tool(description=(
    "在知识库中检索。query 为中文/英文问题；topk 为返回条数（1-100）；"
    "use_pivot=True 时会尝试 LLM 连接词第二路召回（未配置 LLM 时自动降级为单路 BM25）。"
    "返回 results[{chunk_id, doc_id, rel_path, title, snippet, page_start, score, route}]、"
    "pivots、degraded、reason 与双路候选数。"
))
def search(workspace_id: str, query: str, topk: int = 20, use_pivot: bool = True) -> dict[str, Any]:
    ws = _get_ws(workspace_id)
    if not query.strip():
        raise ValueError("retrieval.empty: query 不能为空")
    budget = Budget(
        ws.workspace_id,
        ws.db.connect(),
        ws.cfg.llm.budget_monthly_usd,
        ws.cfg.llm.budget_per_query_usd,
    )
    return retrieve(
        ws,
        query,
        topk=max(1, min(int(topk), 100)),
        use_pivot=use_pivot,
        provider=None,
        budget=budget,
    )


@mcp_server.tool(description="校验工作区的 Merkle 完整性链，失败时返回首个坏记录的 seq 与 scope。")
def verify_integrity(workspace_id: str) -> dict[str, Any]:
    ws = _get_ws(workspace_id)
    try:
        result = ws.chain.verify()
        anchor_mod.verify_anchor(ws.root)
        ws.state.set_state("normal", "")
        return {"ok": True, **_ws_summary(ws), **result}
    except ChainCorrupt as e:
        ws.state.set_state("tampered", f"Merkle 校验失败: {e}")
        raise ValueError(f"integrity.verify_failed: {e}") from e
    except anchor_mod.AnchorMismatch as e:
        ws.state.set_state("tampered", f"锚点不一致: {e}")
        raise ValueError(f"workspace.anchor_mismatch: {e}") from e


@mcp_server.tool(description="查询 LLM 预算使用情况（daily / monthly / total）。")
def get_budget(workspace_id: str) -> dict[str, Any]:
    ws = _get_ws(workspace_id)
    budget = Budget(
        ws.workspace_id,
        ws.db.connect(),
        ws.cfg.llm.budget_monthly_usd,
        ws.cfg.llm.budget_per_query_usd,
    )
    return budget.snapshot()


@mcp_server.tool(name="delete_document", description="删除文档及其全部切片（需工作区可写）。")
def delete_document_tool(workspace_id: str, doc_id: int) -> dict[str, Any]:
    ws = _get_ws(workspace_id)
    if not ws.state.can_write():
        raise ValueError(f"workspace.{ws.state.state}: 当前状态禁止删除")
    delete_document(ws, doc_id)
    return {"ok": True, "doc_id": doc_id}


def mcp_info() -> dict[str, Any]:
    port = int(os.environ.get("PANHUB_MCP_PORT", "0") or 0)
    return {
        "enabled": port > 0,
        "transport": "streamable-http" if port > 0 else "stdio",
        "host": "127.0.0.1",
        "port": port,
        "url": f"http://127.0.0.1:{port}/mcp" if port > 0 else "",
        "stdio_command": "Panhub.exe mcp",
        "tools": [
            "list_workspaces", "open_workspace", "workspace_status",
            "list_documents", "scan_documents", "index_documents",
            "search", "verify_integrity", "get_budget", "delete_document",
        ],
    }
