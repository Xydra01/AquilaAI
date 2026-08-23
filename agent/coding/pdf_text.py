"""Robust PDF text extraction with MuPDF stderr noise suppressed."""
from __future__ import annotations

import io

_mupdf_quiet = False


def configure_mupdf_quiet() -> None:
    """Stop MuPDF from printing font/image warnings to the terminal."""
    global _mupdf_quiet
    if _mupdf_quiet:
        return
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz  # type: ignore[no-redef]
    tools = getattr(fitz, "TOOLS", None)
    if tools is not None:
        if hasattr(tools, "mupdf_display_errors"):
            tools.mupdf_display_errors(False)
        if hasattr(tools, "mupdf_display_warnings"):
            tools.mupdf_display_warnings(False)
        if hasattr(tools, "reset_mupdf_warnings"):
            tools.reset_mupdf_warnings()
    _mupdf_quiet = True


def extract_pdf_text(file_bytes: bytes) -> str:
    """
    Extract plain text from a PDF byte stream.

    Comic/wiki PDFs often embed emoji/color fonts that trigger harmless MuPDF
    errors; text layers are still collected page by page.
    """
    configure_mupdf_quiet()
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz  # type: ignore[no-redef]

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    parts: list[str] = []
    try:
        for page in doc:
            try:
                chunk = page.get_text("text")
                if not (chunk or "").strip():
                    chunk = page.get_text()
            except Exception:
                chunk = ""
            if (chunk or "").strip():
                parts.append(chunk)
    finally:
        doc.close()
    return "\n".join(parts)


def extract_pdf_text_from_path(path: str) -> str:
    with open(path, "rb") as f:
        return extract_pdf_text(f.read())
