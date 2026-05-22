"""Tests for ml_layer.features.common."""

from ml_layer.features.common import detect_file_type, shannon_entropy


class TestShannonEntropy:
    def test_empty_bytes_returns_zero(self) -> None:
        assert shannon_entropy(b"") == 0.0

    def test_single_byte_repeated_returns_zero(self) -> None:
        # All bytes identical → only one symbol → entropy = 0
        assert shannon_entropy(b"\x00" * 1000) == 0.0

    def test_two_equal_symbols_returns_one(self) -> None:
        # 50/50 split of two symbols → entropy = 1.0 bit
        data = bytes([0, 1] * 500)
        result = shannon_entropy(data)
        assert abs(result - 1.0) < 1e-9

    def test_uniform_256_symbols_returns_eight(self) -> None:
        # All 256 byte values equally → entropy = 8.0 bits
        data = bytes(range(256))
        result = shannon_entropy(data)
        assert abs(result - 8.0) < 1e-9

    def test_single_byte_input(self) -> None:
        assert shannon_entropy(b"\xAB") == 0.0

    def test_returns_float(self) -> None:
        assert isinstance(shannon_entropy(b"hello"), float)

    def test_high_entropy_random_like(self) -> None:
        import os
        data = os.urandom(4096)
        result = shannon_entropy(data)
        # Random data should be close to 8.0
        assert result > 7.0


class TestDetectFileType:
    def test_pdf_magic(self) -> None:
        assert detect_file_type(b"%PDF-1.4 rest") == "pdf"

    def test_pe_magic(self) -> None:
        assert detect_file_type(b"MZ\x90\x00rest") == "pe"

    def test_unknown(self) -> None:
        assert detect_file_type(b"\x7fELF rest") == "unknown"

    def test_empty_bytes(self) -> None:
        assert detect_file_type(b"") == "unknown"

    def test_partial_pdf_magic(self) -> None:
        # Only 4 bytes — not enough for %PDF-
        assert detect_file_type(b"%PDF") == "unknown"

    def test_pdf_takes_priority_over_pe(self) -> None:
        # Starts with %PDF- regardless of anything after
        assert detect_file_type(b"%PDF-MZ") == "pdf"
