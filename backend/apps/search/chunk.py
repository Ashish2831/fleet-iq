from __future__ import annotations

from pathlib import Path

SOP_DIR = Path(__file__).resolve().parent / "sops"


def chunk_markdown(text: str, *, size: int = 700, overlap: int = 80) -> list[dict]:
    """Split on headings, then window long sections. Keep heading on each chunk."""
    blocks: list[tuple[str, str]] = []
    heading = ""
    buf: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            if buf:
                blocks.append((heading, "\n".join(buf).strip()))
                buf = []
            heading = line.lstrip("#").strip()
        else:
            buf.append(line)
    if buf:
        blocks.append((heading, "\n".join(buf).strip()))

    chunks = []
    for heading, body in blocks:
        if not body:
            continue
        start = 0
        while start < len(body):
            piece = body[start : start + size]
            chunks.append({"heading": heading, "text": piece.strip()})
            if start + size >= len(body):
                break
            start += size - overlap
    return chunks


def load_sops() -> list[dict]:
    docs = []
    if not SOP_DIR.exists():
        return docs
    for path in sorted(SOP_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        title = raw.splitlines()[0].lstrip("#").strip() if raw else path.stem
        doc_type = path.stem.split("-")[0]
        docs.append({"doc_id": path.stem, "title": title, "source": path.name, "doc_type": doc_type, "text": raw})
    return docs
