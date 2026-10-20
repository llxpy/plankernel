"""REST 路由：workspaces / documents / retrieval / budget / diagnostics / health。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.errors import AppError, error_response
from app.deps import registry
from app.index.service import delete_document, index_documents, scan_documents
from app.integrity.chain import ChainCorrupt
from app.retrieval.engine import retrieve
from app.workspace import anchor as anchor_mod
from app.workspace.locking import WorkspaceLocked
from app.workspace.state import StateMachine

router = APIRouter(prefix="/api/v1")


# ---------- health ----------
@router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> dict:
    return {
        "status": "ok",
        "workspaces": [
            {"id": w.workspace_id, "name": w.cfg.name, "state": w.state.state}
            for w in registry.list()
        ],
    }


# ---------- workspaces ----------
class InitBody(BaseModel):
    root_path: str
    name: str = ""
    index_path: str = ""


class OpenBody(BaseModel):
    root_path: str
    force: bool = False


def _ws_summary(w) -> dict:
    return {
        "id": w.workspace_id,
        "name": w.cfg.name,
        "root_path": str(w.root),
        "state": w.state.state,
        "reason": w.state.reason,
    }


@router.get("/workspaces")
def list_workspaces() -> dict:
    return {"workspaces": [_ws_summary(w) for w in registry.list()]}


@router.post("/workspaces/init")
def init_workspace(body: InitBody) -> dict:
    try:
        cfg = anchor_mod.initialize(Path(body.root_path), body.name or Path(body.root_path).name,
                                    "")
    except FileExistsError as e:
        raise AppError("workspace.state_invalid", str(e)) from e
    except anchor_mod.WorkspaceNotInitialized as e:
        raise AppError("path.inaccessible", str(e)) from e
    ws = registry.open(Path(body.root_path))
    return {"id": cfg.workspace_id, "root_path": str(ws.root), "state": ws.state.state}


@router.post("/workspaces/open")
def open_workspace(body: OpenBody) -> dict:
    try:
        ws = registry.open(Path(body.root_path), force_lock=body.force)
    except anchor_mod.WorkspaceNotInitialized as e:
        raise AppError("workspace.not_found", str(e)) from e
    except anchor_mod.AnchorMismatch as e:
        raise AppError("workspace.anchor_mismatch", str(e)) from e
    return _ws_summary(ws)


@router.get("/workspaces/{workspace_id}")
def workspace_detail(workspace_id: str) -> dict:
    ws = registry.get(workspace_id)
    return {**_ws_summary(ws), "config": {
        "retrieval": vars(ws.cfg.retrieval), "llm": {k: v for k, v in vars(ws.cfg.llm).items() if k != "api_key_ref"},
    }, "stats": ws.stats()}


@router.post("/workspaces/{workspace_id}/close")
def close_workspace(workspace_id: str) -> dict:
    registry.close(workspace_id)
    return {"ok": True}


@router.get("/workspaces/{workspace_id}/state")
def workspace_state(workspace_id: str) -> dict:
    return registry.get(workspace_id).state.snapshot()


@router.post("/workspaces/{workspace_id}/verify")
def verify_workspace(workspace_id: str) -> dict:
    ws = registry.get(workspace_id)
    try:
        result = ws.chain.verify()
        anchor_mod.verify_anchor(ws.root)
        ws.state.set_state("normal", "")
        return {"ok": True, **result}
    except ChainCorrupt as e:
        ws.state.set_state("tampered", f"Merkle 校验失败: {e}")
        raise AppError("integrity.verify_failed", str(e), {"seq": e.seq, "scope": e.scope}) from e
    except anchor_mod.AnchorMismatch as e:
        ws.state.set_state("tampered", f"锚点不一致: {e}")
        raise AppError("workspace.anchor_mismatch", str(e)) from e


@router.post("/workspaces/{workspace_id}/remap")
def remap_workspace(workspace_id: str) -> dict:
    raise AppError("unsupported.operation", "迁移重映射将在后续版本提供")


# ---------- documents ----------
class ScanBody(BaseModel):
    force: bool = False


class IndexBody(BaseModel):
    doc_ids: list[int] = Field(default_factory=list)


@router.post("/workspaces/{workspace_id}/documents/scan")
def documents_scan(workspace_id: str, body: ScanBody) -> dict:
    ws = registry.get(workspace_id)
    if not ws.state.can_write():
        raise AppError("workspace.detached" if ws.state.state == "detached" else "workspace.tampered",
                       f"当前状态 {ws.state.state} 禁止写索引: {ws.state.reason}")
    return scan_documents(ws, force=body.force)


@router.post("/workspaces/{workspace_id}/documents/index")
def documents_index(workspace_id: str, body: IndexBody) -> dict:
    ws = registry.get(workspace_id)
    if not ws.state.can_write():
        raise AppError("workspace.detached" if ws.state.state == "detached" else "workspace.tampered",
                       f"当前状态 {ws.state.state} 禁止写索引: {ws.state.reason}")
    return index_documents(ws, body.doc_ids or None)


@router.get("/workspaces/{workspace_id}/documents")
def documents_list(workspace_id: str) -> dict:
    ws = registry.get(workspace_id)
    conn = ws.db.connect()
    rows = conn.execute(
        "SELECT doc_id, rel_path, status, size_bytes, page_count, parser_version, error_msg, "
        "created_at, indexed_at FROM docs WHERE workspace_id=? ORDER BY rel_path",
        (workspace_id,),
    ).fetchall()
    return {"documents": [dict(r) for r in rows]}


@router.delete("/workspaces/{workspace_id}/documents/{doc_id}")
def documents_delete(workspace_id: str, doc_id: int) -> dict:
    ws = registry.get(workspace_id)
    if not ws.state.can_write():
        raise AppError("workspace.tampered", "当前状态禁止删除")
    delete_document(ws, doc_id)
    return {"ok": True}


# ---------- retrieval ----------
class RetrievalBody(BaseModel):
    query: str = Field(min_length=1, max_length=512)
    topk: int = Field(default=0, ge=0, le=100)
    alpha: float | None = Field(default=None, ge=0, le=1)
    use_pivot: bool = True


@router.post("/workspaces/{workspace_id}/retrieval")
def retrieval(workspace_id: str, body: RetrievalBody, request: Request) -> dict:
    ws = registry.get(workspace_id)
    provider = getattr(request.app.state, "llm_provider", None)
    budget = getattr(request.app.state, "llm_budget", None)
    if budget is None:
        from app.llm.budget import Budget
        budget = Budget(ws.workspace_id, ws.db.connect(),
                        ws.cfg.llm.budget_monthly_usd, ws.cfg.llm.budget_per_query_usd)
        request.app.state.llm_budget = budget
    result = retrieve(ws, body.query, topk=body.topk or None, alpha=body.alpha,
                      use_pivot=body.use_pivot, provider=provider, budget=budget)
    return result


@router.get("/workspaces/{workspace_id}/budget")
def budget_snapshot(workspace_id: str, request: Request) -> dict:
    from app.llm.budget import Budget

    ws = registry.get(workspace_id)
    budget = Budget(ws.workspace_id, ws.db.connect(),
                    ws.cfg.llm.budget_monthly_usd, ws.cfg.llm.budget_per_query_usd)
    return budget.snapshot()


@router.get("/workspaces/{workspace_id}/chain")
def chain_info(workspace_id: str) -> dict:
    ws = registry.get(workspace_id)
    return ws.chain.head()


# ---------- llm ----------
class LLMTestBody(BaseModel):
    endpoint: str = ""
    model: str = ""
    api_key: str = ""


@router.post("/llm/test")
def llm_test(body: LLMTestBody) -> dict:
    import time as _t

    from app.llm.provider import LLMProvider

    p = LLMProvider(body.endpoint, body.api_key, body.model)
    t0 = _t.perf_counter()
    r = p.generate_pivots("测试连接")
    return {"ok": not r.degraded, "latency_ms": int((_t.perf_counter() - t0) * 1000),
            "degraded": r.degraded, "reason": r.reason, "pivots": r.pivots}
