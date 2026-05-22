"""Shared pytest fixtures for ML Layer tests."""

from __future__ import annotations

import io
import struct

import pikepdf
import pytest


def _build_pdf(*, add_javascript: bool = False, add_openaction: bool = False) -> bytes:
    """Construct a minimal valid PDF in memory using pikepdf."""
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))

    if add_javascript:
        js_stream = pikepdf.Stream(pdf, b"app.alert('eval(unescape(test))')")
        js_action = pikepdf.Dictionary(
            Type=pikepdf.Name("/Action"),
            S=pikepdf.Name("/JavaScript"),
            JS=js_stream,
        )
        pdf.Root["/Names"] = pikepdf.Dictionary(
            JavaScript=pikepdf.Dictionary(
                Names=pikepdf.Array([pikepdf.String("test"), js_action])
            )
        )

    if add_openaction:
        oa_action = pikepdf.Dictionary(
            Type=pikepdf.Name("/Action"),
            S=pikepdf.Name("/JavaScript"),
            JS=pikepdf.String("this.print()"),
        )
        pdf.Root["/OpenAction"] = oa_action

    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


@pytest.fixture()
def minimal_pdf_bytes() -> bytes:
    """Minimal valid single-page PDF (no malicious content)."""
    return _build_pdf()


@pytest.fixture()
def malicious_pdf_bytes() -> bytes:
    """PDF containing /JavaScript and /OpenAction."""
    return _build_pdf(add_javascript=True, add_openaction=True)


@pytest.fixture()
def corrupt_pdf_bytes() -> bytes:
    """Bytes that are not a valid PDF."""
    return b"NOT A PDF\x00\xff" + struct.pack(">I", 0xDEADBEEF)
