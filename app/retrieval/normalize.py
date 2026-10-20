"""query 归一化：NFC、全半角、空白合并、长度上限、停用词。"""
from __future__ import annotations

import re
import unicodedata

MAX_QUERY_LEN = 512

_STOPWORDS = {"的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
              "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
              "这", "那", "与", "及", "或", "等", "对", "把", "被", "从", "向", "为", "以",
              "the", "a", "an", "of", "to", "in", "on", "and", "or", "is", "are", "for"}


def normalize(query: str) -> tuple[str, list[str]]:
    q = unicodedata.normalize("NFC", query.strip())
    q = q[:MAX_QUERY_LEN]
    out: list[str] = []
    for ch in q:
        code = ord(ch)
        if code == 0x3000:
            out.append(" ")
        elif 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch.lower())
    q = re.sub(r"\s+", " ", "".join(out)).strip()
    terms = [t for t in q.split(" ") if t and t not in _STOPWORDS]
    return q, terms


def escape_fts5(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def build_match_query(terms: list[str]) -> str:
    """FTS5 MATCH 字符串：jieba 细粒度切词后逐 token OR 连接，短语转义。"""
    import jieba

    seen: set[str] = set()
    parts: list[str] = []
    for t in terms:
        if not t.strip():
            continue
        subs = jieba.lcut_for_search(t)
        for sub in subs:
            sub = sub.strip()
            if not sub or sub in seen:
                continue
            seen.add(sub)
            parts.append(escape_fts5(sub))
    return " OR ".join(parts) if parts else '""'
