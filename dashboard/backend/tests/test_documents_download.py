"""Unicode-safe Content-Disposition headers."""
from dashboard.backend.routes.documents import _content_disposition_filename


def test_ascii_filename() -> None:
    header = _content_disposition_filename("readme.md")
    assert 'filename="readme.md"' in header
    assert "filename*=UTF-8" in header


def test_unicode_filename_uses_rfc5987() -> None:
    header = _content_disposition_filename("设计稿.png")
    assert "filename*=" in header
    assert "%" in header  # percent-encoded UTF-8
    assert 'filename="设计稿.png"' not in header
