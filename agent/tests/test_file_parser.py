import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from file_parser import process_local_attachments

def test_missing_file():
    chunks, images = process_local_attachments(["/path/to/nowhere/fake_file.txt"])
    
    assert len(chunks) == 0
    assert len(images) == 0

def test_text_chunking_math(tmp_path):
    massive_file = tmp_path / "massive_log.txt"
    content = "A" * 200000
    massive_file.write_text(content, encoding="utf-8")
    
    # Process the file
    chunks, images = process_local_attachments([str(massive_file)])
    
    assert len(chunks) == 3
    
    assert len(chunks[0]) <= 90000
    assert len(chunks[1]) <= 90000
    assert len(chunks[2]) <= 90000
    
    assert len(images) == 0

def test_image_encoding(tmp_path):
    import base64
    
    dummy_image = tmp_path / "test_image.jpg"
    dummy_image.write_bytes(b"fake_image_bytes")
    
    chunks, images = process_local_attachments([str(dummy_image)])
    
    assert len(images) == 1
    assert len(chunks) == 0
    
    expected_b64 = base64.b64encode(b"fake_image_bytes").decode("utf-8")
    assert images[0] == expected_b64


def test_csv_parsing(tmp_path):
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("name,value\nfoo,1\nbar,2\n", encoding="utf-8")
    chunks, images = process_local_attachments([str(csv_file)])
    assert len(images) == 0
    assert len(chunks) == 1
    assert "foo" in chunks[0]
    assert "name" in chunks[0] and "foo" in chunks[0]


def test_html_parsing(tmp_path):
    html_file = tmp_path / "page.html"
    html_file.write_text(
        "<html><body><script>x</script><p>Visible text</p></body></html>",
        encoding="utf-8",
    )
    chunks, images = process_local_attachments([str(html_file)])
    assert "Visible text" in chunks[0]
    assert "script" not in chunks[0].lower() or "x" not in chunks[0]


def test_oversize_file_skipped(tmp_path):
    from file_parser import MAX_FILE_BYTES

    big = tmp_path / "huge.txt"
    big.write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    chunks, images = process_local_attachments([str(big)])
    assert len(chunks) == 1
    assert "exceeds" in chunks[0].lower() or "skipped" in chunks[0].lower()