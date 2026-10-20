"""规则切块：结构边界优先，jieba token 预算收尾；content_seg 入 FTS5。"""
from __future__ import annotations

import hashlib

import jieba

jieba.setLogLevel(60)  # 静默初始化日志
jieba.initialize()  # 同步预加载词典：避免后台建缓存线程与测试/退出竞争
from app.config import ParserCfg  # noqa: E402
from app.ingest.parsers import ParsedDoc  # noqa: E402


def estimate_tokens(text: str) -> int:
    words = len(jieba.lcut(text[:2000]))
    return int(words * 1.3 + len(text) * 0.4)


def seg_for_index(text: str) -> str:
    return " ".join(t for t in jieba.lcut_for_search(text) if t.strip())[:64 * 400]


def chunk_document(doc: ParsedDoc, cfg: ParserCfg) -> list[dict]:
    target = cfg.chunk_target_tokens
    overlap = cfg.chunk_overlap_tokens
    blocks = doc.blocks or [{"text": doc.text, "kind": "paragraph", "title": doc.title}]
    out: list[dict] = []

    def split_long(text: str, title: str, kind: str, page_start: int | None) -> None:
        tokens = [t for t in jieba.lcut(text) if t.strip()]
        cur: list[str] = []
        cur_len = 0
        emitted = 0
        for tok in tokens:
            tl = estimate_tokens(tok) + 1
            if cur_len + tl > target and cur:
                body = "".join(cur)
                out.append(_mk(body, title, kind, page_start, emitted))
                emitted += 1
                cur = cur[-(overlap // 2):] if overlap > 0 else []
                cur_len = sum(estimate_tokens(t) + 1 for t in cur)
            cur.append(tok)
            cur_len += tl
        if cur:
            body = "".join(cur)
            out.append(_mk(body, title, kind, page_start, emitted))

    for block in blocks:
        text = block["text"].strip()
        if not text:
            continue
        title = block.get("title") or doc.title
        kind = block.get("kind", "paragraph")
        page_start = block.get("page_start")
        if kind == "table" or estimate_tokens(text) <= target:
            out.append(_mk(text, title, kind, page_start, 0))
        else:
            split_long(text, title, kind, page_start)
    return out


def _mk(content: str, title: str, kind: str, page_start: int | None, seq: int) -> dict:
    content = content.strip()
    seg = seg_for_index(content)
    h = hashlib.sha256(f"{title}|{seq}|{content}".encode()).hexdigest()
    return {
        "title": title[:200],
        "content": content,
        "content_seg": seg,
        "token_count": estimate_tokens(content),
        "seq": seq,
        "page_start": page_start,
        "merge_strategy": "rule",
        "hash": h,
        "kind": kind,
    }
