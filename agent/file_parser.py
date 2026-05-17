import os
import base64
import csv
import io
import mimetypes
from pathlib import Path

import fitz
import docx

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_CHARS_PER_CHUNK = 90000
MAX_CSV_ROWS = 200

TEXT_EXTENSIONS = {
    ".txt", ".py", ".md", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".html", ".htm", ".css", ".js", ".ts", ".tsx", ".jsx", ".xml", ".sh",
    ".bat", ".ps1", ".rs", ".go", ".java", ".c", ".cpp", ".h", ".hpp",
    ".sql", ".log", ".rst",
}


def _read_bytes(path: str) -> tuple[bytes, str] | None:
    if not os.path.exists(path):
        return None
    file_name = os.path.basename(path)
    size = os.path.getsize(path)
    if size > MAX_FILE_BYTES:
        return None
    with open(path, "rb") as f:
        return f.read(), file_name


def _wrap_text(file_name: str, text: str) -> str:
    return f"--- START FILE: {file_name} ---\n{text}\n--- END FILE ---"


def _parse_image(file_bytes: bytes, mime_type: str) -> dict:
    b64 = base64.b64encode(file_bytes).decode("utf-8")
    return {"type": "image", "payload": b64, "mime": mime_type or "image/jpeg"}


def _parse_pdf(file_bytes: bytes, file_name: str) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    extracted = "".join(page.get_text() for page in doc)
    return _wrap_text(file_name, extracted)


def _parse_docx(file_bytes: bytes, file_name: str) -> str:
    document = docx.Document(io.BytesIO(file_bytes))
    parts = []
    for para in document.paragraphs:
        if para.text.strip():
            parts.append(para.text.strip())
    for table in document.tables:
        for row in table.rows:
            row_data = []
            for cell in row.cells:
                if cell.text.strip() and cell.text.strip() not in row_data:
                    row_data.append(cell.text.strip())
            if row_data:
                parts.append(" | ".join(row_data))
    return _wrap_text(file_name, "\n".join(parts))


def _parse_csv(file_bytes: bytes, file_name: str) -> str:
    text = file_bytes.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    lines = []
    for i, row in enumerate(reader):
        if i >= MAX_CSV_ROWS:
            lines.append(f"... [truncated after {MAX_CSV_ROWS} rows]")
            break
        lines.append(", ".join(row))
    return _wrap_text(file_name, "\n".join(lines))


def _parse_xlsx(file_bytes: bytes, file_name: str) -> str:
    try:
        import openpyxl
    except ImportError:
        return (
            f"[System: Cannot parse {file_name} — install openpyxl for Excel support]"
        )
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    parts = []
    for sheet in wb.worksheets:
        parts.append(f"## Sheet: {sheet.title}")
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i >= MAX_CSV_ROWS:
                parts.append(f"... [truncated after {MAX_CSV_ROWS} rows]")
                break
            parts.append(", ".join(str(c) if c is not None else "" for c in row))
    wb.close()
    return _wrap_text(file_name, "\n".join(parts))


def _parse_html(file_bytes: bytes, file_name: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return file_bytes.decode("utf-8", errors="replace")
    soup = BeautifulSoup(file_bytes.decode("utf-8", errors="replace"), "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return _wrap_text(file_name, soup.get_text(separator="\n", strip=True))


def _parse_text(file_bytes: bytes, file_name: str) -> str:
    return _wrap_text(file_name, file_bytes.decode("utf-8", errors="replace"))


def _dispatch_parse(path: str, file_bytes: bytes, file_name: str, mime_type: str | None):
    ext = Path(file_name).suffix.lower()

    if mime_type and mime_type.startswith("image/"):
        return _parse_image(file_bytes, mime_type)

    if mime_type == "application/pdf" or ext == ".pdf":
        try:
            return {"type": "text", "payload": _parse_pdf(file_bytes, file_name)}
        except Exception as e:
            return {"type": "text", "payload": f"[System: Could not parse PDF {file_name} - {e}]"}

    if ext == ".docx":
        try:
            return {"type": "text", "payload": _parse_docx(file_bytes, file_name)}
        except Exception as e:
            return {"type": "text", "payload": f"[System: Could not parse DOCX {file_name} - {e}]"}

    if ext == ".csv":
        try:
            return {"type": "text", "payload": _parse_csv(file_bytes, file_name)}
        except Exception as e:
            return {"type": "text", "payload": f"[System: Could not parse CSV {file_name} - {e}]"}

    if ext == ".xlsx":
        return {"type": "text", "payload": _parse_xlsx(file_bytes, file_name)}

    if ext in (".html", ".htm") or (mime_type and "html" in mime_type):
        return {"type": "text", "payload": _parse_html(file_bytes, file_name)}

    if ext in TEXT_EXTENSIONS or (mime_type and mime_type.startswith("text/")):
        return {"type": "text", "payload": _parse_text(file_bytes, file_name)}

    try:
        return {"type": "text", "payload": _parse_text(file_bytes, file_name)}
    except Exception:
        return {
            "type": "text",
            "payload": f"[System: Unsupported or binary file type for {file_name}]",
        }


def process_local_attachments(file_paths):
    """Parse local files into text chunks and base64 image payloads for the agent."""
    text_payloads = []
    image_payloads = []

    for path in file_paths:
        result = _read_bytes(path)
        if result is None:
            file_name = os.path.basename(path)
            if os.path.exists(path) and os.path.getsize(path) > MAX_FILE_BYTES:
                text_payloads.append(
                    f"[System: File {file_name} exceeds {MAX_FILE_BYTES // (1024*1024)}MB limit and was skipped]"
                )
            continue

        file_bytes, file_name = result
        mime_type, _ = mimetypes.guess_type(path)
        parsed = _dispatch_parse(path, file_bytes, file_name, mime_type)

        if parsed["type"] == "image":
            image_payloads.append(parsed["payload"])
        else:
            text_payloads.append(parsed["payload"])

    combined_text = "\n\n".join(text_payloads)
    text_chunks = []
    if combined_text.strip():
        for i in range(0, len(combined_text), MAX_CHARS_PER_CHUNK):
            text_chunks.append(combined_text[i : i + MAX_CHARS_PER_CHUNK])

    return text_chunks, image_payloads
