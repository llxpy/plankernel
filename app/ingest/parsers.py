"""解析器：pdf/docx/xlsx 多级降级，统一返回 {text, title, page, structure}。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PARSER_VERSION = "1.0.0"


@dataclass
class ParsedDoc:
    text: str
    title: str = ""
    pages: int = 0
    structure: str = "paragraph"  # paragraph / table / mixed
    blocks: list[dict] = field(default_factory=list)
    parser_used: str = ""


class ParseError(Exception):
    """doc.parse_failed"""


def parse_file(path: Path) -> ParsedDoc:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix == ".docx":
        return parse_docx(path)
    if suffix in (".xlsx", ".xlsm"):
        return parse_xlsx(path)
    if suffix in (".txt", ".md", ".log", ".csv"):
        return parse_text(path)
    raise ParseError(f"不支持的格式: {suffix}")


def parse_pdf(path: Path) -> ParsedDoc:
    errors: list[str] = []
    for name in ("pypdf", "pdfplumber", "pymupdf"):
        try:
            if name == "pypdf":
                from pypdf import PdfReader

                reader = PdfReader(str(path))
                blocks = []
                for i, page in enumerate(reader.pages):
                    t = page.extract_text() or ""
                    if t.strip():
                        blocks.append({"text": t, "page_start": i + 1, "page_end": i + 1, "kind": "page"})
                if blocks:
                    return ParsedDoc(
                        text="\n\n".join(b["text"] for b in blocks),
                        title=path.stem, pages=len(reader.pages),
                        blocks=blocks, parser_used=f"pdf:{name}")
                errors.append("pypdf 空文本")
            elif name == "pdfplumber":
                import pdfplumber

                blocks = []
                with pdfplumber.open(str(path)) as pdf:
                    for i, page in enumerate(pdf.pages):
                        t = page.extract_text() or ""
                        if t.strip():
                            blocks.append({"text": t, "page_start": i + 1, "page_end": i + 1, "kind": "page"})
                if blocks:
                    return ParsedDoc(
                        text="\n\n".join(b["text"] for b in blocks),
                        title=path.stem, pages=len(blocks),
                        blocks=blocks, parser_used=f"pdf:{name}")
            elif name == "pymupdf":
                import fitz

                doc = fitz.open(str(path))
                blocks = []
                for i, page in enumerate(doc):
                    t = page.get_text()
                    if t.strip():
                        blocks.append({"text": t, "page_start": i + 1, "page_end": i + 1, "kind": "page"})
                doc.close()
                if blocks:
                    return ParsedDoc(
                        text="\n\n".join(b["text"] for b in blocks),
                        title=path.stem, pages=len(blocks),
                        blocks=blocks, parser_used="pdf:pymupdf")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {e}")
    raise ParseError("pdf 解析全部降级失败: " + "; ".join(errors))


def parse_docx(path: Path) -> ParsedDoc:
    errors: list[str] = []
    try:
        import docx

        d = docx.Document(str(path))
        blocks = []
        for para in d.paragraphs:
            t = para.text.strip()
            if not t:
                continue
            style = (para.style.name or "").lower() if para.style is not None else ""
            heading = ""
            for h in range(1, 4):
                if f"heading {h}" in style:
                    heading = t
                    break
            blocks.append({"text": t, "title": heading, "kind": "heading" if heading else "paragraph"})
        # 表格
        for table in d.tables:
            rows = []
            for row in table.rows:
                rows.append("|".join(c.text.strip() for c in row.cells))
            if rows:
                blocks.append({"text": "\n".join(rows), "kind": "table"})
        if blocks:
            text = "\n\n".join(b["text"] for b in blocks)
            title = next((b["title"] for b in blocks if b.get("title")), path.stem)
            return ParsedDoc(text=text, title=title, blocks=blocks, parser_used="docx:python-docx")
        errors.append("python-docx 空文本")
    except Exception as e:  # noqa: BLE001
        errors.append(f"python-docx: {e}")
    try:
        import docx2txt

        text = docx2txt.process(str(path))
        if text.strip():
            return ParsedDoc(text=text, title=path.stem, parser_used="docx:docx2txt")
        errors.append("docx2txt 空文本")
    except Exception as e:  # noqa: BLE001
        errors.append(f"docx2txt: {e}")
    raise ParseError("docx 解析全部降级失败: " + "; ".join(errors))


def parse_xlsx(path: Path) -> ParsedDoc:
    try:
        import openpyxl

        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        blocks = []
        for ws in wb.worksheets:
            lines = [f"[Sheet:{ws.title}]"]
            for row in ws.iter_rows(values_only=True):
                cells = [str(c) if c is not None else "" for c in row]
                if any(cells):
                    lines.append("|".join(cells))
            if len(lines) > 1:
                blocks.append({"text": "\n".join(lines), "kind": "table", "sheet": ws.title})
        wb.close()
        if blocks:
            return ParsedDoc(
                text="\n\n".join(b["text"] for b in blocks),
                title=path.stem, blocks=blocks, structure="table",
                parser_used="xlsx:openpyxl")
        raise ParseError("xlsx 无数据")
    except ParseError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ParseError(f"xlsx 解析失败: {e}") from e


def parse_text(path: Path) -> ParsedDoc:
    raw = path.read_bytes()
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            text = raw.decode(enc)
            return ParsedDoc(text=text, title=path.stem, parser_used=f"text:{enc}")
        except (UnicodeDecodeError, LookupError):
            continue
    raise ParseError("文本编码无法识别")
