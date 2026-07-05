"""Static PDF feature extraction with pikepdf.

The public surface is ``PDFFeatureExtractor`` and ``FEATURE_ORDER``. Training and
inference must share ``FEATURE_ORDER`` so the vector fed to the ONNX model always
matches what the model was trained on. ``FEATURE_ORDER`` is append-only.
"""

from __future__ import annotations

import io
import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import pikepdf

from ml_layer.features.common import shannon_entropy


@dataclass
class _Signals:
    js_found: bool = False
    openaction_found: bool = False
    aa_found: bool = False
    embedded_file_found: bool = False
    launch_found: bool = False
    acroform_found: bool = False
    xfa_found: bool = False
    submitform_found: bool = False
    goto_remote_found: bool = False
    jbig2_found: bool = False
    richmedia_found: bool = False
    uri_count: int = 0
    uri_external_count: int = 0
    object_stream_count: int = 0
    encoding_layers: int = 0
    stream_count: int = 0
    suspicious_js_count: int = 0
    stream_entropies: list[float] = field(default_factory=list)
    uri_domains: set[str] = field(default_factory=set)


# Append-only. The first block is legacy static structure; the "modern" block
# targets today's multi-page, JS-free, URL-driven malware; the exploit block is
# informed by the CIC-Evasive feature set. Files trained on an older, shorter
# FEATURE_ORDER stay compatible because the analyzer slices to the model width.
FEATURE_ORDER: list[str] = [
    "entropy",
    "max_stream_entropy",
    "pdf_object_count",
    "pdf_stream_count",
    "pdf_page_count",
    "pdf_header_version",
    "pdf_has_javascript",
    "pdf_has_openaction",
    "pdf_has_auto_action",
    "pdf_has_embedded_file",
    "pdf_has_launch",
    "pdf_has_acroform",
    "pdf_has_xfa",
    "pdf_suspicious_js_count",
    "pdf_encoding_layers",
    "pdf_uri_count",
    "pdf_parse_error",
    "pdf_uri_external_count",
    "pdf_uri_distinct_domains",
    "pdf_has_submitform",
    "pdf_has_goto_remote",
    "pdf_object_stream_count",
    "pdf_incremental_updates",
    "pdf_has_jbig2",
    "pdf_has_richmedia",
]

_SUSPICIOUS_JS_PATTERNS: list[re.Pattern[bytes]] = [
    re.compile(rb"eval\s*\("),
    re.compile(rb"unescape\s*\("),
    re.compile(rb"String\.fromCharCode\s*\("),
]

_ENCODING_FILTERS = frozenset(
    {
        "/FlateDecode",
        "/ASCIIHexDecode",
        "/ASCII85Decode",
        "/LZWDecode",
        "/RunLengthDecode",
    }
)

_EOF_MARKER = b"%%EOF"
_JBIG2_FILTER = "/JBIG2Decode"
_OBJECT_STREAM_TYPE = "/ObjStm"
_RICHMEDIA = "/RichMedia"

# Performance caps: entropy stabilises within the first megabyte; oversized
# streams are images/fonts, not scripts; and the security-relevant objects of a
# huge benign document appear early, so the walk is bounded.
_ENTROPY_SAMPLE_BYTES: int = 1_000_000
_MAX_STREAM_COMPRESSED_BYTES: int = 5_000_000
_MAX_STREAM_BODY_BYTES: int = 512_000
_MAX_BFS_OBJECTS: int = 3_000


def _zero_features() -> dict[str, float]:
    return {k: 0.0 for k in FEATURE_ORDER}


def _compute_filter_depth(filters: Any) -> int:
    if isinstance(filters, pikepdf.Array):
        return sum(1 for f in filters if str(f) in _ENCODING_FILTERS)
    return 1 if str(filters) in _ENCODING_FILTERS else 0


def _read_stream_body(obj: pikepdf.Stream) -> bytes | None:
    try:
        length_obj = obj.get("/Length")
        if length_obj is not None and int(length_obj) > _MAX_STREAM_COMPRESSED_BYTES:
            return None
        body = obj.read_bytes()
        return body[:_MAX_STREAM_BODY_BYTES] if body else body
    except Exception:  # noqa: BLE001
        return None


def _get_stream_dict_values(obj: pikepdf.Stream) -> list[Any]:
    try:
        return list(obj.stream_dict.values())  # type: ignore[operator]
    except Exception:  # noqa: BLE001
        return []


def _scan_js_content(value: Any, suspicious_js_count: list[int]) -> None:
    body: bytes | None = None
    try:
        body = value.read_bytes()
    except Exception:  # noqa: BLE001
        pass
    if body is None:
        try:
            body = bytes(value)
        except Exception:  # noqa: BLE001
            pass
    if body is not None:
        for pattern in _SUSPICIOUS_JS_PATTERNS:
            suspicious_js_count[0] += len(pattern.findall(body))


def _record_uri(value: Any, sig: _Signals) -> None:
    try:
        url = str(value).strip()
    except Exception:  # noqa: BLE001
        return
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https"):
        sig.uri_external_count += 1
        if parsed.netloc:
            sig.uri_domains.add(parsed.netloc.lower())


def _record_action(value: Any, sig: _Signals) -> None:
    name = str(value)
    if name == "/SubmitForm":
        sig.submitform_found = True
    elif name in ("/GoToR", "/GoToE"):
        sig.goto_remote_found = True


def _filters_contain(filters: Any, name: str) -> bool:
    if isinstance(filters, pikepdf.Array):
        return any(str(f) == name for f in filters)
    return str(filters) == name


def _is_richmedia(key_str: str, value: Any) -> bool:
    return key_str == _RICHMEDIA or (key_str == "/Subtype" and str(value) == _RICHMEDIA)


def _inspect_dict_entry(key_str: str, value: Any, sig: _Signals) -> None:
    if _is_richmedia(key_str, value):
        sig.richmedia_found = True
    if key_str in ("/JS", "/JavaScript"):
        sig.js_found = True
        counter = [0]
        _scan_js_content(value, counter)
        sig.suspicious_js_count += counter[0]
    elif key_str == "/OpenAction":
        sig.openaction_found = True
    elif key_str == "/AA":
        sig.aa_found = True
    elif key_str in ("/EmbeddedFile", "/EmbeddedFiles", "/EF"):
        sig.embedded_file_found = True
    elif key_str == "/Launch":
        sig.launch_found = True
    elif key_str == "/AcroForm":
        sig.acroform_found = True
    elif key_str == "/XFA":
        sig.xfa_found = True
    elif key_str == "/URI":
        sig.uri_count += 1
        _record_uri(value, sig)
    elif key_str == "/S":
        _record_action(value, sig)


def _inspect_stream(obj: pikepdf.Stream, sig: _Signals, queue: deque[Any]) -> None:
    sig.stream_count += 1
    filters = obj.get("/Filter")
    if filters is not None:
        sig.encoding_layers = max(sig.encoding_layers, _compute_filter_depth(filters))
        if _filters_contain(filters, _JBIG2_FILTER):
            sig.jbig2_found = True
    if str(obj.get("/Type")) == _OBJECT_STREAM_TYPE:
        sig.object_stream_count += 1
    body = _read_stream_body(obj)
    if body is not None:
        sig.stream_entropies.append(shannon_entropy(body))
        for pattern in _SUSPICIOUS_JS_PATTERNS:
            sig.suspicious_js_count += len(pattern.findall(body))
    for value in _get_stream_dict_values(obj):
        queue.append(value)


def _extract_object_signals(pdf: pikepdf.Pdf, *, sig: _Signals) -> None:
    visited: set[int] = set()
    queue: deque[Any] = deque(pdf.objects)

    while queue:
        if len(visited) >= _MAX_BFS_OBJECTS:
            break

        obj = queue.popleft()
        obj_id = id(obj)
        if obj_id in visited:
            continue
        visited.add(obj_id)

        if isinstance(obj, pikepdf.Stream):
            _inspect_stream(obj, sig, queue)
        elif isinstance(obj, pikepdf.Dictionary):
            for key, value in obj.items():
                _inspect_dict_entry(str(key), value, sig)
                queue.append(value)
        elif isinstance(obj, pikepdf.Array):
            for item in obj:
                queue.append(item)


class PDFFeatureExtractor:
    def extract(self, data: bytes) -> dict[str, float]:
        features = _zero_features()

        try:
            pdf = pikepdf.open(io.BytesIO(data))
        except pikepdf.PdfError:
            features["pdf_parse_error"] = 1.0
            return features

        features["entropy"] = shannon_entropy(data[:_ENTROPY_SAMPLE_BYTES])

        try:
            features["pdf_header_version"] = float(pdf.pdf_version)
        except (ValueError, AttributeError):
            pass

        try:
            features["pdf_page_count"] = float(len(pdf.pages))
        except Exception:  # noqa: BLE001
            pass

        features["pdf_object_count"] = float(len(list(pdf.objects)))
        features["pdf_incremental_updates"] = float(data.count(_EOF_MARKER))

        sig = _Signals()
        _extract_object_signals(pdf, sig=sig)

        features["pdf_stream_count"] = float(sig.stream_count)
        features["max_stream_entropy"] = max(sig.stream_entropies) if sig.stream_entropies else 0.0
        features["pdf_has_javascript"] = 1.0 if sig.js_found else 0.0
        features["pdf_has_openaction"] = 1.0 if sig.openaction_found else 0.0
        features["pdf_has_auto_action"] = 1.0 if sig.aa_found else 0.0
        features["pdf_has_embedded_file"] = 1.0 if sig.embedded_file_found else 0.0
        features["pdf_has_launch"] = 1.0 if sig.launch_found else 0.0
        features["pdf_has_acroform"] = 1.0 if sig.acroform_found else 0.0
        features["pdf_has_xfa"] = 1.0 if sig.xfa_found else 0.0
        features["pdf_suspicious_js_count"] = float(sig.suspicious_js_count)
        features["pdf_encoding_layers"] = float(sig.encoding_layers)
        features["pdf_uri_count"] = float(sig.uri_count)
        features["pdf_uri_external_count"] = float(sig.uri_external_count)
        features["pdf_uri_distinct_domains"] = float(len(sig.uri_domains))
        features["pdf_has_submitform"] = 1.0 if sig.submitform_found else 0.0
        features["pdf_has_goto_remote"] = 1.0 if sig.goto_remote_found else 0.0
        features["pdf_object_stream_count"] = float(sig.object_stream_count)
        features["pdf_has_jbig2"] = 1.0 if sig.jbig2_found else 0.0
        features["pdf_has_richmedia"] = 1.0 if sig.richmedia_found else 0.0

        return features
