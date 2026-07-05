"""Tests for training.fetch_arxiv_benign (mocked HTTP)."""

from __future__ import annotations

from pathlib import Path

from training.fetch_arxiv_benign import download_pdf, fetch, list_recent_ids

_PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\n%%EOF"

_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><id>http://arxiv.org/abs/2401.00001v1</id></entry>
  <entry><id>http://arxiv.org/abs/2401.00002v1</id></entry>
  <entry><other>no id here</other></entry>
</feed>"""


class _FakeResponse:
    def __init__(self, *, text: str = "", content: bytes = b"") -> None:
        self.text = text
        self.content = content


class _FakeClient:
    def __init__(self, fail: tuple[str, ...] = ()) -> None:
        self.fail = set(fail)

    def get(self, url: str, params: dict[str, str] | None = None) -> _FakeResponse:
        if "/api/query" in url:
            return _FakeResponse(text=_ATOM)
        arxiv_id = url.rsplit("/pdf/", 1)[-1]
        if arxiv_id in self.fail:
            return _FakeResponse(content=b"<html>rate limited</html>")
        return _FakeResponse(content=_PDF)


class TestListRecentIds:
    def test_parses_ids_and_skips_entries_without_id(self) -> None:
        ids = list_recent_ids(_FakeClient(), ["cs.CR"], max_results=10)
        assert ids == ["2401.00001v1", "2401.00002v1"]


class TestDownloadPdf:
    def test_returns_pdf_bytes(self) -> None:
        assert download_pdf(_FakeClient(), "2401.00001v1") == _PDF

    def test_returns_none_when_not_a_pdf(self) -> None:
        assert download_pdf(_FakeClient(fail=("2401.00001v1",)), "2401.00001v1") is None


class TestFetch:
    def test_writes_then_skips(self, tmp_path: Path) -> None:
        res = fetch(str(tmp_path), categories=["cs.CR"], sleep=0, client=_FakeClient())
        assert res == {"written": 2, "skipped": 0, "failed": 0}
        assert (tmp_path / "arxiv_2401.00001v1.pdf").read_bytes() == _PDF

        res2 = fetch(str(tmp_path), categories=["cs.CR"], sleep=0, client=_FakeClient())
        assert res2 == {"written": 0, "skipped": 2, "failed": 0}

    def test_counts_non_pdf_failures(self, tmp_path: Path) -> None:
        client = _FakeClient(fail=("2401.00001v1",))
        res = fetch(str(tmp_path), categories=["cs.CR"], sleep=0, client=client)
        assert res["failed"] == 1
        assert res["written"] == 1
