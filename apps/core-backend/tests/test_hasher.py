import hashlib

from backend.services.hasher import compute_sha256


class TestComputeSha256:
    """Tests for the SHA-256 hashing service."""

    async def test_known_hash(self) -> None:
        """SHA-256 of a known payload must match the reference digest."""
        payload = b"Hello, Zero-Trust!"
        expected = hashlib.sha256(payload).hexdigest()

        result = await compute_sha256(payload)

        assert result == expected

    async def test_empty_bytes(self) -> None:
        """SHA-256 of empty bytes must return the well-known empty digest."""
        empty_digest = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

        result = await compute_sha256(b"")

        assert result == empty_digest

    async def test_returns_lowercase_hex_64_chars(self) -> None:
        """Digest must always be lowercase hex, 64 characters."""
        result = await compute_sha256(b"test")

        assert len(result) == 64
        assert result == result.lower()
        assert all(c in "0123456789abcdef" for c in result)

    async def test_deterministic(self) -> None:
        """Same input must always produce the same digest."""
        payload = b"deterministic-check"

        result_a = await compute_sha256(payload)
        result_b = await compute_sha256(payload)

        assert result_a == result_b

    async def test_different_inputs_different_hashes(self) -> None:
        """Different inputs must produce different digests."""
        result_a = await compute_sha256(b"file_a")
        result_b = await compute_sha256(b"file_b")

        assert result_a != result_b
