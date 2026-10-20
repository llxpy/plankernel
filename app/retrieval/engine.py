"""pivot 缓存与双路召回融合：score / rrf 可切换，retrieval_score 落表。"""
from __future__ import annotations

import hashlib
import json
import time
import uuid

from app.config import RetrievalCfg
from app.llm.budget import Budget, BudgetExceeded, estimate_cost_usd
from app.llm.provider import LLMProvider, PROMPT_VERSION
from app.retrieval.normalize import build_match_query, normalize
from app.workspace.manager import Workspace


class RetrievalError(Exception):
    """retrieval.failed"""


def query_hash(q_norm: str, model: str, workspace_id: str) -> str:
    return hashlib.sha256(f"{q_norm}|{model}|{PROMPT_VERSION}|{workspace_id}".encode()).hexdigest()


def get_pivots(ws: Workspace, q_norm: str, provider: LLMProvider | None,
               budget: Budget | None) -> tuple[list[str], bool]:
    """返回 (pivots, degraded)。缓存命中绝不重复调用 LLM。"""
    if not q_norm:
        return [], True
    model = ws.cfg.llm.model
    h = query_hash(q_norm, model, ws.workspace_id)
    conn = ws.db.connect()
    row = conn.execute("SELECT pivots_json, hit_count FROM pivot_cache WHERE query_hash=?", (h,)).fetchone()
    if row:
        conn.execute("UPDATE pivot_cache SET hit_count=hit_count+1 WHERE query_hash=?", (h,))
        conn.commit()
        return json.loads(row["pivots_json"]), False
    if provider is None or budget is None or not ws.cfg.llm.enabled:
        return [], True
    try:
        budget.check(0.001)
    except BudgetExceeded:
        return [], True
    result = provider.generate_pivots(q_norm)
    if result.degraded or not result.pivots:
        return [], True
    cost = estimate_cost_usd(result.input_tokens, result.output_tokens)
    budget.record(result.input_tokens, result.output_tokens, cost)
    conn.execute(
        "INSERT OR REPLACE INTO pivot_cache(query_hash,workspace_id,query_text,pivots_json,model,"
        "prompt_version,input_tokens,output_tokens,cost_usd,created_at,hit_count) VALUES (?,?,?,?,?,?,?,?,?,0)",
        (h, ws.workspace_id, q_norm, json.dumps(result.pivots, ensure_ascii=False), model,
         PROMPT_VERSION, result.input_tokens, result.output_tokens, cost, int(time.time())),
    )
    conn.commit()
    ws.chain.append("meta", "pivot", {"query_hash": h})
    return result.pivots, False


def _minmax(scores: list[float]) -> dict[float, float]:
    if not scores:
        return {}
    mx, mn = max(scores), min(scores)
    if mx == mn:
        return {s: 1.0 for s in scores}
    return {s: (mx - s) / (mx - mn) for s in scores}  # bm25 越小越相关


def _fts_match(conn, match_q: str, title_w: float, body_w: float, topk: int) -> list[tuple[int, float]]:
    if not match_q or match_q == '""':
        return []
    try:
        rows = conn.execute(
            "SELECT chunk_id, bm25(chunks_fts, ?, ?) AS s FROM chunks_fts "
            "WHERE chunks_fts MATCH ? ORDER BY s LIMIT ?",
            (title_w, body_w, match_q, topk),
        ).fetchall()
        return [(r["chunk_id"], r["s"]) for r in rows]
    except Exception:  # noqa: BLE001
        return []


def retrieve(ws: Workspace, query: str, topk: int | None = None, alpha: float | None = None,
             use_pivot: bool = True, provider: LLMProvider | None = None,
             budget: Budget | None = None) -> dict:
    cfg: RetrievalCfg = ws.cfg.retrieval
    topk = min(topk or cfg.default_topk, 100)
    alpha = cfg.alpha if alpha is None else alpha
    q_norm, terms = normalize(query)
    if not q_norm:
        return {"query": query, "results": [], "degraded": True, "reason": "query 为空"}

    pivots, pivot_degraded = ([], True)
    if use_pivot:
        pivots, pivot_degraded = get_pivots(ws, q_norm, provider, budget)
    else:
        pivot_degraded = False  # 用户显式关闭第二路，不算降级

    conn = ws.db.connect()
    run_id = str(uuid.uuid4())
    now = int(time.time())
    r1 = _fts_match(conn, build_match_query(terms), cfg.bm25_title_weight, cfg.bm25_body_weight, cfg.rerank_topk)
    pivot_terms = [p for p in pivots if p not in " ".join(terms)]
    r2 = _fts_match(conn, build_match_query(pivot_terms), cfg.bm25_title_weight, cfg.bm25_body_weight,
                    cfg.rerank_topk) if pivots else []

    n1, n2 = _minmax([s for _, s in r1]), _minmax([s for _, s in r2])
    with ws.write_lock:
        with conn:
            for rank, (cid, s) in enumerate(r1):
                conn.execute(
                    "INSERT OR REPLACE INTO retrieval_score(query_run_id,chunk_id,route,rank,raw_score,norm_score,created_at)"
                    " VALUES (?,?,?,?,?,?,?)", (run_id, cid, "original", rank, s, n1.get(s, 0), now))
            for rank, (cid, s) in enumerate(r2):
                conn.execute(
                    "INSERT OR REPLACE INTO retrieval_score(query_run_id,chunk_id,route,rank,raw_score,norm_score,created_at)"
                    " VALUES (?,?,?,?,?,?,?)", (run_id, cid, "pivot", rank, s, n2.get(s, 0), now))

            fused: dict[int, float] = {}
            if cfg.fusion == "rrf":
                k = cfg.rrf_k
                for rank, (cid, _) in enumerate(r1):
                    fused[cid] = fused.get(cid, 0) + 1 / (k + rank + 1)
                for rank, (cid, _) in enumerate(r2):
                    fused[cid] = fused.get(cid, 0) + 1 / (k + rank + 1)
            else:
                for cid, s in r1:
                    fused[cid] = alpha * n1.get(s, 0)
                for cid, s in r2:
                    fused[cid] = fused.get(cid, 0) + (1 - alpha) * n2.get(s, 0)
            for rank, (cid, fs) in enumerate(sorted(fused.items(), key=lambda x: -x[1])):
                conn.execute(
                    "INSERT OR REPLACE INTO retrieval_score(query_run_id,chunk_id,route,rank,raw_score,norm_score,created_at)"
                    " VALUES (?,?,?,?,?,?,?)", (run_id, cid, "fused", rank, 0.0, fs, now))

    rows = conn.execute(
        "SELECT chunk_id, fused FROM retrieval_score WHERE query_run_id=? AND route='fused' "
        "ORDER BY fused DESC LIMIT ?", (run_id, topk),
    ).fetchall()

    results = []
    for r in rows:
        if r["fused"] < cfg.min_score:
            continue
        chunk = conn.execute(
            "SELECT c.chunk_id, c.doc_id, c.title, c.content, c.page_start, c.token_count, "
            "d.rel_path, d.status FROM chunks c JOIN docs d ON d.doc_id=c.doc_id WHERE c.chunk_id=?",
            (r["chunk_id"],),
        ).fetchone()
        if not chunk or chunk["status"] != "ready":
            continue
        route = "both"
        routes = conn.execute(
            "SELECT route FROM retrieval_score WHERE query_run_id=? AND chunk_id=? AND route!='fused'",
            (run_id, r["chunk_id"]),
        ).fetchall()
        rl = {x["route"] for x in routes}
        route = "+".join(sorted(rl))
        results.append({
            "chunk_id": chunk["chunk_id"],
            "doc_id": chunk["doc_id"],
            "rel_path": chunk["rel_path"],
            "title": chunk["title"],
            "snippet": chunk["content"][:280],
            "page_start": chunk["page_start"],
            "score": round(r["fused"], 6),
            "route": route,
        })

    conn.execute("DELETE FROM retrieval_score WHERE query_run_id=? AND created_at<?",
                 (run_id, now - 86400))
    conn.commit()
    return {
        "query": query,
        "q_norm": q_norm,
        "run_id": run_id,
        "results": results,
        "pivots": pivots,
        "degraded": pivot_degraded,
        "reason": "pivot 降级为单路原始 BM25" if pivot_degraded and use_pivot else "",
        "routes": {"original": len(r1), "pivot": len(r2)},
    }
