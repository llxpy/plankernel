"""品牌审查：所有网页与 UI 文案不得出现指定禁用词（见 FORBIDDEN 常量）。"""
from __future__ import annotations

from pathlib import Path

FORBIDDEN = "\u9ed1\u9a6c"
ROOT = Path(__file__).resolve().parent.parent
WEB_SUFFIXES = {".html", ".js", ".jsx", ".css", ".md"}


def _web_files() -> list[Path]:
    targets: list[Path] = [ROOT / "README.md", ROOT / "frontend" / "index.html"]
    src = ROOT / "frontend" / "src"
    if src.exists():
        targets += [p for p in src.rglob("*") if p.is_file()]
    dist = ROOT / "frontend" / "dist"
    if dist.exists():
        targets += [p for p in dist.rglob("*") if p.is_file()]
    return [p for p in targets if p.suffix.lower() in WEB_SUFFIXES]


def test_web_pages_do_not_contain_forbidden_text():
    offenders = []
    for path in _web_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if FORBIDDEN in text:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, f"发现禁用词「{FORBIDDEN}」: {offenders}"
