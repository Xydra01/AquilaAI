import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from gui_formatting import format_attachment_notice_html


def test_attachment_notice_lists_files_and_chunks():
    html = format_attachment_notice_html(
        ["notes.md", "data.csv"],
        text_chunk_count=2,
        image_count=0,
    )
    assert "notes.md" in html
    assert "2 text chunk" in html


def test_attachment_notice_empty_when_no_attachments():
    assert format_attachment_notice_html([]) == ""
