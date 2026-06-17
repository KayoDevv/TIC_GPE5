"""PDF static feature extraction using pikepdf.

All public surface is the ``PDFFeatureExtractor`` class and the
``FEATURE_ORDER`` constant.  Both training and inference must use the
same ``FEATURE_ORDER`` so that the numpy vector fed to the ONNX model
is always aligned with what was used during training.
"""

from __future__ import annotations

import io
import re
from collections import deque
from typing import Any

import pikepdf

from ml_layer.features.common import shannon_entropy

# Canonical feature order — never reorder; append only.
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
]

# Patterns that indicate obfuscated / malicious JavaScript inside a PDF stream.
_SUSPICIOUS_JS_PATTERNS: list[re.Pattern[bytes]] = [
    re.compile(rb"eval\s*\("),
    re.compile(rb"unescape\s*\("),
    re.compile(rb"String\.fromCharCode\s*\("),
]

# Filter names that are stacked in malicious PDFs to hide payloads.
_ENCODING_FILTERS = frozenset(
    {
        "/FlateDecode",
        "/ASCIIHexDecode",
        "/ASCII85Decode",
        "/LZWDecode",
        "/RunLengthDecode",
    }
)

# ── Performance caps ──────────────────────────────────────────────────────────
# Sample only the first 1 MB of raw file bytes for whole-file entropy.
# Entropy stabilises quickly; reading more just burns CPU on large documents.
_ENTROPY_SAMPLE_BYTES: int = 1_000_000

# Maximum *compressed* stream length (bytes) we will attempt to decompress.
# Streams larger than this are almost certainly images or fonts — not JS.
# Skipping them avoids multi-second decompression for huge embedded objects.
_MAX_STREAM_COMPRESSED_BYTES: int = 5_000_000  # 5 MB

# After decompression, cap body at this many bytes for entropy / JS scanning.
_MAX_STREAM_BODY_BYTES: int = 512_000  # 512 KB

# Maximum PDF objects visited by the BFS.  Large benign documents can have
# tens of thousands of objects; the security-relevant ones appear early.
_MAX_BFS_OBJECTS: int = 3_000
# ─────────────────────────────────────────────────────────────────────────────


def _zero_features() -> dict[str, float]:
    return {k: 0.0 for k in FEATURE_ORDER}


def _compute_filter_depth(filters: Any) -> int:
    """Return the encoding filter stack depth for a /Filter value.

    *filters* is either a ``pikepdf.Array`` (stacked filters) or a single
    ``pikepdf.Name``.  Only filters in ``_ENCODING_FILTERS`` contribute.
    """
    if isinstance(filters, pikepdf.Array):
        return sum(1 for f in filters if str(f) in _ENCODING_FILTERS)  # type: ignore
    return 1 if str(filters) in _ENCODING_FILTERS else 0


def _read_stream_body(obj: pikepdf.Stream) -> bytes | None:
    """Return the decoded body of *obj* (capped to ``_MAX_STREAM_BODY_BYTES``).

    Returns ``None`` on any read error or when the compressed size exceeds
    ``_MAX_STREAM_COMPRESSED_BYTES`` (those are images / fonts, not scripts).
    """
    try:
        # Check the on-disk (compressed) length before decompressing.
        length_obj = obj.get("/Length")
        if length_obj is not None and int(length_obj) > _MAX_STREAM_COMPRESSED_BYTES:
            return None
        body = obj.read_bytes()
        return body[:_MAX_STREAM_BODY_BYTES] if body else body
    except Exception:  # noqa: BLE001
        return None


def _get_stream_dict_values(obj: pikepdf.Stream) -> list[Any]:
    """Return ``list(obj.stream_dict.values())``, or ``[]`` on any error."""
    try:
        return list(obj.stream_dict.values())  # type: ignore[operator]
    except Exception:  # noqa: BLE001
        return []


def _scan_js_content(value: Any, suspicious_js_count: list[int]) -> None:
    """Extract and scan JavaScript content for suspicious patterns.

    Uses try/except so that both direct and indirect (reference-wrapped)
    pikepdf stream objects are handled correctly.
    """
    body: bytes | None = None

    # Try reading as a stream first (handles pikepdf.Stream and indirect refs).
    try:
        body = value.read_bytes()
    except Exception:  # noqa: BLE001
        pass

    # Fall back to raw bytes for inline string objects.
    if body is None:
        try:
            body = bytes(value)
        except Exception:  # noqa: BLE001
            pass

    if body is not None:
        for pattern in _SUSPICIOUS_JS_PATTERNS:
            suspicious_js_count[0] += len(pattern.findall(body))


def _extract_object_signals(
    pdf: pikepdf.Pdf,
    *,
    js_found: list[bool],
    openaction_found: list[bool],
    aa_found: list[bool],
    embedded_file_found: list[bool],
    launch_found: list[bool],
    acroform_found: list[bool],
    xfa_found: list[bool],
    uri_count: list[int],
    encoding_layers: list[int],
    stream_count: list[int],
    stream_entropies: list[float],
    suspicious_js_count: list[int],
) -> None:
    """Iterative BFS walk over all PDF objects to collect security signals.

    Uses a visited-id set to break circular references that would otherwise
    cause unbounded recursion in a naive recursive approach.

    The walk is capped at ``_MAX_BFS_OBJECTS`` to bound runtime on very large
    benign documents (government reports, textbooks, etc.) that can contain
    tens of thousands of embedded font / image objects.
    """
    visited: set[int] = set()
    queue: deque[Any] = deque(pdf.objects)

    while queue:
        # Hard cap — stop once we've visited enough objects.
        if len(visited) >= _MAX_BFS_OBJECTS:
            break

        obj = queue.popleft()
        obj_id = id(obj)
        if obj_id in visited:
            continue
        visited.add(obj_id)

        if isinstance(obj, pikepdf.Stream):
            stream_count[0] += 1

            # Encoding filter stack depth.
            filters = obj.get("/Filter")
            if filters is not None:
                depth = _compute_filter_depth(filters)
                encoding_layers[0] = max(encoding_layers[0], depth)

            # Stream body entropy + suspicious JS scan (with size caps).
            body = _read_stream_body(obj)
            if body is not None:
                stream_entropies.append(shannon_entropy(body))
                # Scan every stream body for JS obfuscation patterns —
                # malicious PDFs embed JS in any stream, not just /JS-keyed ones.
                for pattern in _SUSPICIOUS_JS_PATTERNS:
                    suspicious_js_count[0] += len(pattern.findall(body))

            # Enqueue stream dictionary entries for further inspection.
            for value in _get_stream_dict_values(obj):
                queue.append(value)

        elif isinstance(obj, pikepdf.Dictionary):
            for key, value in obj.items():
                key_str = str(key)

                if key_str in ("/JS", "/JavaScript"):
                    js_found[0] = True
                    _scan_js_content(value, suspicious_js_count)

                if key_str == "/OpenAction":
                    openaction_found[0] = True
                if key_str == "/AA":
                    aa_found[0] = True
                # /EmbeddedFiles = Names tree for attachments
                # /EF = embedded file dict inside a file spec
                if key_str in ("/EmbeddedFile", "/EmbeddedFiles", "/EF"):
                    embedded_file_found[0] = True
                if key_str == "/Launch":
                    launch_found[0] = True
                if key_str == "/AcroForm":
                    acroform_found[0] = True
                if key_str == "/XFA":
                    xfa_found[0] = True
                if key_str == "/URI":
                    uri_count[0] += 1

                queue.append(value)

        elif isinstance(obj, pikepdf.Array):
            for item in obj:  # type: ignore[attr-defined]
                queue.append(item)


class PDFFeatureExtractor:
    """Extract 16 static security features from a PDF byte payload.

    This class is **synchronous** — in an async context wrap calls with
    ``asyncio.to_thread(extractor.extract, data)``.
    """

    def extract(self, data: bytes) -> dict[str, float]:
        """Return a feature dict aligned with ``FEATURE_ORDER``.

        On any ``pikepdf.PdfError`` (corrupt / encrypted PDF) returns all
        zeros with ``pdf_parse_error = 1.0`` appended as a side-channel key
        (not part of ``FEATURE_ORDER`` — used by the dispatcher for tagging).
        """
        features = _zero_features()

        try:
            pdf = pikepdf.open(io.BytesIO(data))
        except pikepdf.PdfError:
            features["pdf_parse_error"] = 1.0
            return features

        # Entropy is only meaningful for parseable PDFs.
        # Sample at most _ENTROPY_SAMPLE_BYTES — entropy stabilises quickly
        # and reading the full file on a 50 MB document is prohibitively slow.
        features["entropy"] = shannon_entropy(data[:_ENTROPY_SAMPLE_BYTES])

        # Header version (e.g. "%PDF-1.7" → 1.7).
        try:
            features["pdf_header_version"] = float(pdf.pdf_version)
        except (ValueError, AttributeError):
            pass

        # Page count.
        try:
            features["pdf_page_count"] = float(len(pdf.pages))
        except Exception:  # noqa: BLE001
            pass

        # Object count (count all indirect objects).
        features["pdf_object_count"] = float(len(list(pdf.objects)))

        # Accumulators for iterative walk.
        js_found: list[bool] = [False]
        openaction_found: list[bool] = [False]
        aa_found: list[bool] = [False]
        embedded_file_found: list[bool] = [False]
        launch_found: list[bool] = [False]
        acroform_found: list[bool] = [False]
        xfa_found: list[bool] = [False]
        uri_count: list[int] = [0]
        encoding_layers: list[int] = [0]
        stream_count: list[int] = [0]
        stream_entropies: list[float] = []
        suspicious_js_count: list[int] = [0]

        _extract_object_signals(
            pdf,
            js_found=js_found,
            openaction_found=openaction_found,
            aa_found=aa_found,
            embedded_file_found=embedded_file_found,
            launch_found=launch_found,
            acroform_found=acroform_found,
            xfa_found=xfa_found,
            uri_count=uri_count,
            encoding_layers=encoding_layers,
            stream_count=stream_count,
            stream_entropies=stream_entropies,
            suspicious_js_count=suspicious_js_count,
        )

        features["pdf_stream_count"] = float(stream_count[0])
        features["max_stream_entropy"] = max(stream_entropies) if stream_entropies else 0.0
        features["pdf_has_javascript"] = 1.0 if js_found[0] else 0.0
        features["pdf_has_openaction"] = 1.0 if openaction_found[0] else 0.0
        features["pdf_has_auto_action"] = 1.0 if aa_found[0] else 0.0
        features["pdf_has_embedded_file"] = 1.0 if embedded_file_found[0] else 0.0
        features["pdf_has_launch"] = 1.0 if launch_found[0] else 0.0
        features["pdf_has_acroform"] = 1.0 if acroform_found[0] else 0.0
        features["pdf_has_xfa"] = 1.0 if xfa_found[0] else 0.0
        features["pdf_suspicious_js_count"] = float(suspicious_js_count[0])
        features["pdf_encoding_layers"] = float(encoding_layers[0])
        features["pdf_uri_count"] = float(uri_count[0])

        return features
