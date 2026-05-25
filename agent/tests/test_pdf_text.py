import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pdf_text import configure_mupdf_quiet, extract_pdf_text

pymupdf = pytest.importorskip("pymupdf")


def test_configure_mupdf_quiet_idempotent():
    configure_mupdf_quiet()
    configure_mupdf_quiet()
    tools = pymupdf.TOOLS
    assert tools.mupdf_display_errors() is False
    assert tools.mupdf_display_warnings() is False


def test_extract_pdf_text_minimal_pdf():
    # Minimal valid PDF with one page containing "Hello"
    minimal = (
        b"%PDF-1.4\n"
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
        b"/Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >> >>endobj\n"
        b"4 0 obj<< /Length 44 >>stream\n"
        b"BT /F1 12 Tf 50 100 Td (Hello) Tj ET\n"
        b"endstream endobj\n"
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n"
        b"0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
        b"0000000250 00000 n \n0000000345 00000 n \n"
        b"trailer<< /Size 6 /Root 1 0 R >>\nstartxref\n420\n%%EOF"
    )
    text = extract_pdf_text(minimal)
    assert "Hello" in text
