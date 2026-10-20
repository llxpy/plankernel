"""FTS5 索引维护：文档扫描、增量入库、切片写入、触发器同步。"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

from app.ingest.chunker import chunk_document
from app.ingest.parsers import ParseError, parse_file
from app.workspace.manager import Workspace

SUPPORTED = {".pdf", ".docx", ".xlsx", ".xlsm", ".txt", ".md", ".log", ".csv"}


def scan_documents(ws: Workspace, force: bool = False) -> dict:
    """扫描工作区目录，按 (rel_path, content_sha256) 增量登记 docs。"""
    conn = ws.db.connect()
    known = {
        r["rel_path"]: r
        for r in conn.execute(
            "SELECT doc_id, rel_path, content_sha256, status FROM docs WHERE workspace_id=?",
            (ws.workspace_id,),
        ).fetchall()
    }
    added, updated, skipped = 0, 0, 0
    now = int(time.time())
    for f in sorted(ws.root.rglob("*")):
        if not f.is_file() or ".kbengine" in f.parts:
            continue
        if f.suffix.lower() not in SUPPORTED:
            continue
        rel = f.relative_to(ws.root).as_posix()
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
        if rel in known and known[rel]["content_sha256"] == sha and not force:
            continue
        if rel in known and known[rel]["content_sha256"] != sha:
            conn.execute(
                "UPDATE docs SET content_sha256=?, status='pending', updated_at=? WHERE doc_id=?",
                (sha, now, known[rel]["doc_id"]),
            )
            updated += 1
        else:
            conn.execute(
                "INSERT INTO docs(workspace_id,rel_path,abs_path,content_sha256,size_bytes,mime,"
                "status,parser_version,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ws.workspace_id, rel, str(f), sha, f.stat().st_size,
                 f.suffix.lower().lstrip("."), "pending", "", now, now),
            )
            added += 1
    conn.commit()
    ws.chain.append("docs", "scan", {"added": added, "updated": updated})
    return {"added": added, "updated": updated, "skipped": skipped}


def index_documents(ws: Workspace, doc_ids: list[int] | None = None) -> dict:
    """解析 → 切块 → 写 chunks + FTS5（触发器同步）。"""
    conn = ws.db.connect()
    if doc_ids:
        rows = conn.execute(
            "SELECT doc_id, rel_path, abs_path, content_sha256 FROM docs "
            "WHERE workspace_id=? AND doc_id IN (%s)" % ",".join("?" * len(doc_ids)),
            (ws.workspace_id, *doc_ids),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT doc_id, rel_path, abs_path, content_sha256 FROM docs "
            "WHERE workspace_id=? AND status IN ('pending','failed')",
            (ws.workspace_id,),
        ).fetchall()

    ok, failed = 0, 0
    errors: list[dict] = []
    now = int(time.time())
    for r in rows:
        doc_id, abs_path = r["doc_id"], r["abs_path"]
        conn.execute("UPDATE docs SET status='indexing', updated_at=? WHERE doc_id=?", (now, doc_id))
        conn.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
        conn.commit()
        try:
            parsed = parse_file(Path(abs_path))
            chunks = chunk_document(parsed, ws.cfg.parser)
            for c in chunks:
                conn.execute(
                    "INSERT INTO chunks(workspace_id,doc_id,seq,parent_id,title,content,content_seg,"
                    "token_count,byte_offset,page_start,page_end,merge_strategy,hash,created_at) "
                    "VALUES (?,?,?,NULL,?,?,?,?,?,?,?,?,?,?)",
                    (ws.workspace_id, doc_id, c["seq"], c["title"], c["content"], c["content_seg"],
                     c["token_count"], 0, c["page_start"], c.get("page_end"), c["merge_strategy"],
                     c["hash"], now),
                )
            conn.execute(
                "UPDATE docs SET status='ready', parser_version=?, page_count=?, indexed_at=?, "
                "error_msg=NULL, updated_at=? WHERE doc_id=?",
                (parsed.parser_used, parsed.pages, now, now, doc_id),
            )
            ok += 1
        except (ParseError, Exception) as e:  # noqa: BLE001
            conn.execute(
                "UPDATE docs SET status='failed', error_msg=?, updated_at=? WHERE doc_id=?",
                (str(e)[:500], now, doc_id),
            )
            failed += 1
            errors.append({"doc_id": doc_id, "rel_path": r["rel_path"], "error": str(e)[:200]})
        conn.commit()
    if ok:
        ws.chain.append("chunks", "index", {"indexed": ok, "failed": failed})
    return {"indexed": ok, "failed": failed, "errors": errors}


def delete_document(ws: Workspace, doc_id: int) -> None:
    conn = ws.db.connect()
    conn.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
    conn.execute("DELETE FROM docs WHERE doc_id=? AND workspace_id=?", (doc_id, ws.workspace_id))
    conn.commit()
    ws.chain.append("docs", "delete", {"doc_id": doc_id})
