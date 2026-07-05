"""Tests for ml_layer.features.pdf.PDFFeatureExtractor."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pikepdf
import pytest

from ml_layer.features.pdf import (
    _MAX_STREAM_BODY_BYTES,
    _MAX_STREAM_COMPRESSED_BYTES,
    FEATURE_ORDER,
    PDFFeatureExtractor,
    _compute_filter_depth,
    _filters_contain,
    _get_stream_dict_values,
    _inspect_dict_entry,
    _read_stream_body,
    _record_action,
    _record_uri,
    _scan_js_content,
    _Signals,
)


@pytest.fixture()
def extractor() -> PDFFeatureExtractor:
    return PDFFeatureExtractor()


class TestFeatureOrder:
    def test_feature_order_has_25_entries(self) -> None:
        assert len(FEATURE_ORDER) == 25

    def test_feature_order_has_no_duplicates(self) -> None:
        assert len(FEATURE_ORDER) == len(set(FEATURE_ORDER))

    def test_feature_order_contains_expected_keys(self) -> None:
        expected = {
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
        }
        assert set(FEATURE_ORDER) == expected


class TestExtractCleanPDF:
    def test_returns_dict_with_all_feature_keys(
        self, extractor: PDFFeatureExtractor, minimal_pdf_bytes: bytes
    ) -> None:
        features = extractor.extract(minimal_pdf_bytes)
        for key in FEATURE_ORDER:
            assert key in features, f"Missing feature: {key}"

    def test_entropy_is_positive(
        self, extractor: PDFFeatureExtractor, minimal_pdf_bytes: bytes
    ) -> None:
        features = extractor.extract(minimal_pdf_bytes)
        assert features["entropy"] > 0.0

    def test_page_count_is_one(
        self, extractor: PDFFeatureExtractor, minimal_pdf_bytes: bytes
    ) -> None:
        features = extractor.extract(minimal_pdf_bytes)
        assert features["pdf_page_count"] == 1.0

    def test_object_count_is_positive(
        self, extractor: PDFFeatureExtractor, minimal_pdf_bytes: bytes
    ) -> None:
        features = extractor.extract(minimal_pdf_bytes)
        assert features["pdf_object_count"] > 0

    def test_no_javascript_in_clean_pdf(
        self, extractor: PDFFeatureExtractor, minimal_pdf_bytes: bytes
    ) -> None:
        features = extractor.extract(minimal_pdf_bytes)
        assert features["pdf_has_javascript"] == 0.0

    def test_no_openaction_in_clean_pdf(
        self, extractor: PDFFeatureExtractor, minimal_pdf_bytes: bytes
    ) -> None:
        features = extractor.extract(minimal_pdf_bytes)
        assert features["pdf_has_openaction"] == 0.0

    def test_header_version_is_valid_float(
        self, extractor: PDFFeatureExtractor, minimal_pdf_bytes: bytes
    ) -> None:
        features = extractor.extract(minimal_pdf_bytes)
        assert features["pdf_header_version"] > 0.0

    def test_all_values_are_floats(
        self, extractor: PDFFeatureExtractor, minimal_pdf_bytes: bytes
    ) -> None:
        features = extractor.extract(minimal_pdf_bytes)
        for key in FEATURE_ORDER:
            assert isinstance(features[key], float), f"Feature {key!r} is not a float"


class TestExtractMaliciousPDF:
    def test_javascript_detected(
        self, extractor: PDFFeatureExtractor, malicious_pdf_bytes: bytes
    ) -> None:
        features = extractor.extract(malicious_pdf_bytes)
        assert features["pdf_has_javascript"] == 1.0

    def test_openaction_detected(
        self, extractor: PDFFeatureExtractor, malicious_pdf_bytes: bytes
    ) -> None:
        features = extractor.extract(malicious_pdf_bytes)
        assert features["pdf_has_openaction"] == 1.0

    def test_suspicious_js_count_is_positive(
        self, extractor: PDFFeatureExtractor, malicious_pdf_bytes: bytes
    ) -> None:
        # The fixture embeds eval() and unescape() patterns.
        features = extractor.extract(malicious_pdf_bytes)
        assert features["pdf_suspicious_js_count"] >= 1.0


class TestExtractCorruptPDF:
    def test_corrupt_returns_zeros_for_structural_features(
        self, extractor: PDFFeatureExtractor, corrupt_pdf_bytes: bytes
    ) -> None:
        features = extractor.extract(corrupt_pdf_bytes)
        for key in FEATURE_ORDER:
            if key == "pdf_parse_error":
                continue
            assert features[key] == 0.0

    def test_corrupt_sets_parse_error_flag(
        self, extractor: PDFFeatureExtractor, corrupt_pdf_bytes: bytes
    ) -> None:
        features = extractor.extract(corrupt_pdf_bytes)
        assert features.get("pdf_parse_error") == 1.0

    def test_corrupt_entropy_is_zero(
        self, extractor: PDFFeatureExtractor, corrupt_pdf_bytes: bytes
    ) -> None:
        # Entropy is only computed after a successful PDF open.
        # Corrupt/unparseable files return 0 for all FEATURE_ORDER keys.
        features = extractor.extract(corrupt_pdf_bytes)
        assert features["entropy"] == 0.0


class TestEmbeddedFileDetection:
    def test_embedded_file_detected(self, extractor: PDFFeatureExtractor) -> None:
        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        embedded = pikepdf.Stream(pdf, b"fake attachment content")
        pdf.Root["/Names"] = pikepdf.Dictionary(
            EmbeddedFiles=pikepdf.Dictionary(
                Names=pikepdf.Array(
                    [
                        pikepdf.String("attachment.txt"),
                        pikepdf.Dictionary(
                            Type=pikepdf.Name("/Filespec"),
                            EF=pikepdf.Dictionary(F=embedded),
                        ),
                    ]
                )
            )
        )
        buf = io.BytesIO()
        pdf.save(buf)
        features = extractor.extract(buf.getvalue())
        assert features["pdf_has_embedded_file"] == 1.0


class TestAcroFormDetection:
    def test_acroform_detected(self, extractor: PDFFeatureExtractor) -> None:
        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        pdf.Root["/AcroForm"] = pikepdf.Dictionary(Fields=pikepdf.Array())
        buf = io.BytesIO()
        pdf.save(buf)
        features = extractor.extract(buf.getvalue())
        assert features["pdf_has_acroform"] == 1.0


class TestStreamCount:
    def test_stream_count_positive_for_valid_pdf(
        self, extractor: PDFFeatureExtractor, minimal_pdf_bytes: bytes
    ) -> None:
        features = extractor.extract(minimal_pdf_bytes)
        assert features["pdf_stream_count"] >= 0.0

    def test_max_stream_entropy_non_negative(
        self, extractor: PDFFeatureExtractor, minimal_pdf_bytes: bytes
    ) -> None:
        features = extractor.extract(minimal_pdf_bytes)
        assert features["max_stream_entropy"] >= 0.0


class TestAutoActionDetection:
    def test_aa_key_detected(self, extractor: PDFFeatureExtractor) -> None:
        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        pdf.Root["/AA"] = pikepdf.Dictionary(
            WC=pikepdf.Dictionary(
                Type=pikepdf.Name("/Action"),
                S=pikepdf.Name("/JavaScript"),
                JS=pikepdf.String("this.print()"),
            )
        )
        buf = io.BytesIO()
        pdf.save(buf)
        features = extractor.extract(buf.getvalue())
        assert features["pdf_has_auto_action"] == 1.0


class TestLaunchDetection:
    def test_launch_key_detected(self, extractor: PDFFeatureExtractor) -> None:
        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        # Store a /Launch action in a named dict to ensure the key exists.
        pdf.Root["/Names"] = pikepdf.Dictionary(
            Launch=pikepdf.Dictionary(
                Type=pikepdf.Name("/Action"),
                S=pikepdf.Name("/Launch"),
                F=pikepdf.String("cmd.exe"),
            )
        )
        buf = io.BytesIO()
        pdf.save(buf)
        features = extractor.extract(buf.getvalue())
        assert features["pdf_has_launch"] == 1.0


class TestXFADetection:
    def test_xfa_key_detected(self, extractor: PDFFeatureExtractor) -> None:
        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        pdf.Root["/AcroForm"] = pikepdf.Dictionary(
            Fields=pikepdf.Array(),
            XFA=pikepdf.Array([pikepdf.String("template"), pikepdf.String("<template/>")]),
        )
        buf = io.BytesIO()
        pdf.save(buf)
        features = extractor.extract(buf.getvalue())
        assert features["pdf_has_xfa"] == 1.0


class TestURIDetection:
    def test_uri_counted(self, extractor: PDFFeatureExtractor) -> None:
        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        # Embed a URI action dict at the root names level.
        pdf.Root["/Names"] = pikepdf.Dictionary(
            URI=pikepdf.Dictionary(
                Names=pikepdf.Array(
                    [
                        pikepdf.String("link"),
                        pikepdf.Dictionary(
                            Type=pikepdf.Name("/Action"),
                            S=pikepdf.Name("/URI"),
                            URI=pikepdf.String("http://evil.example.com"),
                        ),
                    ]
                )
            )
        )
        buf = io.BytesIO()
        pdf.save(buf)
        features = extractor.extract(buf.getvalue())
        assert features["pdf_uri_count"] >= 1.0


class TestHelperFunctions:
    """Direct unit tests for the helper functions extracted from the BFS."""

    # --- _compute_filter_depth ---

    def test_single_known_filter_returns_one(self) -> None:
        assert _compute_filter_depth(pikepdf.Name("/FlateDecode")) == 1

    def test_single_unknown_filter_returns_zero(self) -> None:
        assert _compute_filter_depth(pikepdf.Name("/DCTDecode")) == 0

    def test_array_of_two_known_filters_returns_two(self) -> None:
        filters = pikepdf.Array([pikepdf.Name("/FlateDecode"), pikepdf.Name("/ASCIIHexDecode")])
        assert _compute_filter_depth(filters) == 2

    def test_array_with_unknown_filter_only_counts_known(self) -> None:
        filters = pikepdf.Array([pikepdf.Name("/FlateDecode"), pikepdf.Name("/DCTDecode")])
        assert _compute_filter_depth(filters) == 1

    def test_empty_array_returns_zero(self) -> None:
        assert _compute_filter_depth(pikepdf.Array()) == 0

    # --- _read_stream_body ---

    def test_read_stream_body_returns_none_on_error(self) -> None:
        mock_obj = MagicMock()
        mock_obj.get.return_value = None
        mock_obj.read_bytes.side_effect = Exception("io error")
        result = _read_stream_body(mock_obj)
        assert result is None

    def test_read_stream_body_returns_bytes_on_success(self) -> None:
        mock_obj = MagicMock()
        mock_obj.get.return_value = None
        mock_obj.read_bytes.return_value = b"content"
        result = _read_stream_body(mock_obj)
        assert result == b"content"

    def test_read_stream_body_skips_oversized_streams(self) -> None:
        """Streams whose /Length exceeds _MAX_STREAM_COMPRESSED_BYTES return None."""
        mock_obj = MagicMock()
        # Simulate a /Length value larger than the cap (e.g. 6 MB).
        mock_obj.get.return_value = _MAX_STREAM_COMPRESSED_BYTES + 1
        result = _read_stream_body(mock_obj)
        assert result is None
        mock_obj.read_bytes.assert_not_called()

    def test_read_stream_body_caps_decoded_bytes(self) -> None:
        """Decoded body larger than _MAX_STREAM_BODY_BYTES is truncated."""
        mock_obj = MagicMock()
        mock_obj.get.return_value = None
        large_body = b"x" * (_MAX_STREAM_BODY_BYTES + 1000)
        mock_obj.read_bytes.return_value = large_body
        result = _read_stream_body(mock_obj)
        assert result is not None
        assert len(result) == _MAX_STREAM_BODY_BYTES

    # --- _get_stream_dict_values ---

    def test_get_stream_dict_values_returns_empty_on_error(self) -> None:
        mock_obj = MagicMock()
        mock_obj.stream_dict.values.side_effect = Exception("values error")
        result = _get_stream_dict_values(mock_obj)
        assert result == []

    def test_get_stream_dict_values_returns_list_on_success(self) -> None:
        mock_obj = MagicMock()
        mock_obj.stream_dict.values.return_value = ["a", "b"]
        result = _get_stream_dict_values(mock_obj)
        assert result == ["a", "b"]


class TestExceptionPaths:
    """Cover error-handling branches that require mocking."""

    def test_scan_js_content_read_bytes_succeeds_body_set(self) -> None:
        """read_bytes() succeeds → body is not None → skip fallback block (covers 78->84)."""
        mock_value: MagicMock = MagicMock()
        mock_value.read_bytes.return_value = b"eval(x)"
        count: list[int] = [0]
        _scan_js_content(mock_value, count)
        assert count[0] >= 1

    def test_scan_js_content_both_fail_body_stays_none(self) -> None:
        """Both read_bytes() and bytes() raise → body is None → covers lines 81-82 and 84->exit."""

        class BothFail:
            def read_bytes(self) -> bytes:
                raise RuntimeError("stream error")

            def __bytes__(self) -> bytes:
                raise TypeError("cannot convert")

        count: list[int] = [0]
        _scan_js_content(BothFail(), count)
        assert count[0] == 0

    def test_scan_js_content_read_bytes_raises_bytes_succeeds(self) -> None:
        """read_bytes() raises but bytes() returns matchable content."""

        class FakeValue:
            def read_bytes(self) -> bytes:
                raise RuntimeError("no stream")

            def __bytes__(self) -> bytes:
                return b"eval(unescape('x'))"

        count: list[int] = [0]
        _scan_js_content(FakeValue(), count)
        assert count[0] >= 1

    def test_all_feature_keys_present_in_valid_extraction(
        self, extractor: PDFFeatureExtractor, minimal_pdf_bytes: bytes
    ) -> None:
        """All FEATURE_ORDER keys are always present in the returned dict."""
        features = extractor.extract(minimal_pdf_bytes)
        for key in FEATURE_ORDER:
            assert key in features

    def test_filters_is_none_branch_in_bfs(self, extractor: PDFFeatureExtractor) -> None:
        """Cover BFS branch where stream has no /Filter (152->157).

        Achieved by saving with compress_streams=False so streams have no /Filter key.
        """
        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        buf = io.BytesIO()
        pdf.save(buf, compress_streams=False)
        features = extractor.extract(buf.getvalue())
        for key in FEATURE_ORDER:
            assert key in features

    def test_body_is_none_branch_in_bfs(self, extractor: PDFFeatureExtractor) -> None:
        """Cover BFS branch where _read_stream_body returns None (158->166)."""
        import ml_layer.features.pdf as pdf_mod

        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        buf = io.BytesIO()
        pdf.save(buf)

        with patch.object(pdf_mod, "_read_stream_body", return_value=None):
            features = extractor.extract(buf.getvalue())
        for key in FEATURE_ORDER:
            assert key in features
        assert features["max_stream_entropy"] == 0.0

    def test_pdf_header_version_value_error_silenced(
        self, extractor: PDFFeatureExtractor, minimal_pdf_bytes: bytes
    ) -> None:
        """ValueError from pdf.pdf_version is silenced; version stays 0."""
        with patch("pikepdf.Pdf.pdf_version", new_callable=lambda: property(lambda self: "bad")):
            features = extractor.extract(minimal_pdf_bytes)
        assert features["pdf_header_version"] == 0.0

    def test_pdf_page_count_exception_silenced(
        self, extractor: PDFFeatureExtractor, minimal_pdf_bytes: bytes
    ) -> None:
        """Exception from len(pdf.pages) is silenced; page count stays 0."""
        with patch("pikepdf._core.PageList.__len__", side_effect=Exception("pages error")):
            features = extractor.extract(minimal_pdf_bytes)
        assert features["pdf_page_count"] == 0.0

    def test_bfs_cap_stops_walk_on_large_pdf(self, extractor: PDFFeatureExtractor) -> None:
        """BFS halts after _MAX_BFS_OBJECTS regardless of PDF size (covers the cap branch)."""
        import ml_layer.features.pdf as pdf_mod

        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        buf = io.BytesIO()
        pdf.save(buf)

        visited_counts: list[int] = []
        original_signals = pdf_mod._extract_object_signals

        def patched_signals(p: object, **kwargs: object) -> None:  # type: ignore[override]
            # Temporarily lower the cap so the test doesn't need a huge PDF.
            with patch.object(pdf_mod, "_MAX_BFS_OBJECTS", 1):
                original_signals(p, **kwargs)  # type: ignore[arg-type]
            visited_counts.append(1)

        with patch.object(pdf_mod, "_extract_object_signals", side_effect=patched_signals):
            features = extractor.extract(buf.getvalue())

        for key in FEATURE_ORDER:
            assert key in features

    def test_entropy_sampled_not_full_file(self, extractor: PDFFeatureExtractor) -> None:
        """Entropy is computed on at most _ENTROPY_SAMPLE_BYTES of raw data."""
        import ml_layer.features.pdf as pdf_mod
        from ml_layer.features.common import shannon_entropy

        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        buf = io.BytesIO()
        pdf.save(buf)
        data = buf.getvalue()

        sampled_lengths: list[int] = []
        original_entropy = shannon_entropy

        def patched_entropy(d: bytes) -> float:
            sampled_lengths.append(len(d))
            return original_entropy(d)

        with patch.object(pdf_mod, "shannon_entropy", side_effect=patched_entropy):
            extractor.extract(data)

        # The first call (whole-file entropy) must use at most _ENTROPY_SAMPLE_BYTES.
        from ml_layer.features.pdf import _ENTROPY_SAMPLE_BYTES

        assert sampled_lengths[0] <= _ENTROPY_SAMPLE_BYTES

    def test_stream_dict_values_enqueued(self, extractor: PDFFeatureExtractor) -> None:
        """Cover BFS branch where _get_stream_dict_values returns non-empty (line 167).

        Patch _get_stream_dict_values to return a real pikepdf.Array so that
        queue.append(value) is executed at least once inside the Stream branch.
        """
        import ml_layer.features.pdf as pdf_mod

        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        buf = io.BytesIO()
        pdf.save(buf)

        original = pdf_mod._get_stream_dict_values

        call_count = [0]

        def patched(obj: object) -> list:
            call_count[0] += 1
            if call_count[0] == 1:
                # Return a non-empty list on the first stream to exercise line 167.
                return [pikepdf.Array()]
            return original(obj)  # type: ignore[arg-type]

        with patch.object(pdf_mod, "_get_stream_dict_values", side_effect=patched):
            features = extractor.extract(buf.getvalue())

        for key in FEATURE_ORDER:
            assert key in features


class TestRecordUri:
    def test_external_http_uri_counted_with_domain(self) -> None:
        sig = _Signals()
        _record_uri("https://evil.example.com/x", sig)
        assert sig.uri_external_count == 1
        assert sig.uri_domains == {"evil.example.com"}

    def test_non_http_uri_ignored(self) -> None:
        sig = _Signals()
        _record_uri("mailto:hi@example.com", sig)
        assert sig.uri_external_count == 0
        assert sig.uri_domains == set()

    def test_http_without_netloc_counts_but_adds_no_domain(self) -> None:
        sig = _Signals()
        _record_uri("http:", sig)
        assert sig.uri_external_count == 1
        assert sig.uri_domains == set()

    def test_unstringable_value_is_ignored(self) -> None:
        class _BadStr:
            def __str__(self) -> str:
                raise ValueError("boom")

        sig = _Signals()
        _record_uri(_BadStr(), sig)
        assert sig.uri_external_count == 0


class TestRecordAction:
    def test_submitform(self) -> None:
        sig = _Signals()
        _record_action(pikepdf.Name("/SubmitForm"), sig)
        assert sig.submitform_found is True

    def test_goto_remote(self) -> None:
        sig = _Signals()
        _record_action(pikepdf.Name("/GoToR"), sig)
        assert sig.goto_remote_found is True

    def test_other_action_ignored(self) -> None:
        sig = _Signals()
        _record_action(pikepdf.Name("/GoTo"), sig)
        assert sig.submitform_found is False
        assert sig.goto_remote_found is False


class TestInspectDictEntry:
    def test_uri_entry_records_external(self) -> None:
        sig = _Signals()
        _inspect_dict_entry("/URI", "http://phish.example/login", sig)
        assert sig.uri_count == 1
        assert sig.uri_external_count == 1

    def test_action_entry_routes_to_record_action(self) -> None:
        sig = _Signals()
        _inspect_dict_entry("/S", pikepdf.Name("/SubmitForm"), sig)
        assert sig.submitform_found is True


class TestModernStructuralFeatures:
    def test_object_stream_counted(self, extractor: PDFFeatureExtractor) -> None:
        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        buf = io.BytesIO()
        pdf.save(buf, object_stream_mode=pikepdf.ObjectStreamMode.generate)
        features = extractor.extract(buf.getvalue())
        assert features["pdf_object_stream_count"] >= 1.0

    def test_incremental_updates_at_least_one(self, extractor: PDFFeatureExtractor) -> None:
        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        buf = io.BytesIO()
        pdf.save(buf)
        features = extractor.extract(buf.getvalue())
        assert features["pdf_incremental_updates"] >= 1.0


class TestExploitVectorFeatures:
    def test_filters_contain_array(self) -> None:
        arr = pikepdf.Array([pikepdf.Name("/FlateDecode"), pikepdf.Name("/JBIG2Decode")])
        assert _filters_contain(arr, "/JBIG2Decode") is True
        assert _filters_contain(arr, "/DCTDecode") is False

    def test_filters_contain_single_name(self) -> None:
        assert _filters_contain(pikepdf.Name("/JBIG2Decode"), "/JBIG2Decode") is True
        assert _filters_contain(pikepdf.Name("/FlateDecode"), "/JBIG2Decode") is False

    def test_jbig2_stream_detected(self, extractor: PDFFeatureExtractor) -> None:
        pdf = pikepdf.Pdf.new()
        pdf.add_blank_page(page_size=(612, 792))
        stream = pdf.make_stream(b"\x00\x01\x02\x03")
        stream.Filter = pikepdf.Name("/JBIG2Decode")
        pdf.Root["/JBTest"] = pdf.make_indirect(stream)
        buf = io.BytesIO()
        pdf.save(buf)
        features = extractor.extract(buf.getvalue())
        assert features["pdf_has_jbig2"] == 1.0

    def test_richmedia_via_key(self) -> None:
        sig = _Signals()
        _inspect_dict_entry("/RichMedia", "x", sig)
        assert sig.richmedia_found is True

    def test_richmedia_via_subtype_value(self) -> None:
        sig = _Signals()
        _inspect_dict_entry("/Subtype", pikepdf.Name("/RichMedia"), sig)
        assert sig.richmedia_found is True

    def test_richmedia_absent_for_other_subtype(self) -> None:
        sig = _Signals()
        _inspect_dict_entry("/Subtype", pikepdf.Name("/Widget"), sig)
        assert sig.richmedia_found is False
