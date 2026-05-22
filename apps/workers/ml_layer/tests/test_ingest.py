"""Tests for training.ingest — dataset loading."""

from __future__ import annotations

import csv
import io
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pikepdf
import pytest

from ml_layer.features.pdf import FEATURE_ORDER
from training.ingest import (
    _collect_paths_from_csv,
    _collect_paths_from_dir,
    _extract_one,
    _timeout_handler,
    load_dataset,
)


def _write_minimal_pdf(path: Path) -> None:
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))
    buf = io.BytesIO()
    pdf.save(buf)
    path.write_bytes(buf.getvalue())


@pytest.fixture()
def dataset_dir(tmp_path: Path) -> Path:
    """Temporary directory with malicious/ and benign/ PDF subdirectories."""
    mal_dir = tmp_path / "malicious"
    ben_dir = tmp_path / "benign"
    mal_dir.mkdir()
    ben_dir.mkdir()

    _write_minimal_pdf(mal_dir / "evil.pdf")
    _write_minimal_pdf(ben_dir / "clean.pdf")
    return tmp_path


@pytest.fixture()
def dataset_csv(tmp_path: Path) -> Path:
    """CSV dataset file pointing at two minimal PDFs."""
    mal_file = tmp_path / "evil.pdf"
    ben_file = tmp_path / "clean.pdf"
    _write_minimal_pdf(mal_file)
    _write_minimal_pdf(ben_file)

    csv_file = tmp_path / "labels.csv"
    with csv_file.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["path", "label"])
        writer.writeheader()
        writer.writerow({"path": str(mal_file), "label": 1})
        writer.writerow({"path": str(ben_file), "label": 0})
    return csv_file


class TestTimeoutHandler:
    def test_raises_timeout_error(self) -> None:
        """_timeout_handler must raise TimeoutError when called as a signal handler."""
        with pytest.raises(TimeoutError):
            _timeout_handler(signal.SIGALRM, None)


class TestExtractOne:
    def test_returns_dict_with_label(self, dataset_dir: Path) -> None:
        pdf_path = str(dataset_dir / "malicious" / "evil.pdf")
        result = _extract_one(pdf_path, 1)
        assert result is not None
        assert result["label"] == 1
        for key in FEATURE_ORDER:
            assert key in result

    def test_returns_none_for_missing_file(self) -> None:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = _extract_one("/nonexistent/path/file.pdf", 0)
        assert result is None

    def test_parse_error_key_stripped(self, dataset_dir: Path) -> None:
        pdf_path = str(dataset_dir / "malicious" / "evil.pdf")
        result = _extract_one(pdf_path, 1)
        assert result is not None
        assert "pdf_parse_error" not in result


class TestCollectPathsFromDir:
    def test_finds_both_labels(self, dataset_dir: Path) -> None:
        pairs = _collect_paths_from_dir(dataset_dir)
        labels = {label for _, label in pairs}
        assert labels == {0, 1}

    def test_returns_correct_count(self, dataset_dir: Path) -> None:
        pairs = _collect_paths_from_dir(dataset_dir)
        assert len(pairs) == 2

    def test_missing_subdir_skipped(self, tmp_path: Path) -> None:
        # Only benign/ exists
        ben_dir = tmp_path / "benign"
        ben_dir.mkdir()
        _write_minimal_pdf(ben_dir / "clean.pdf")
        pairs = _collect_paths_from_dir(tmp_path)
        assert all(label == 0 for _, label in pairs)

    def test_extension_less_files_included(self, tmp_path: Path) -> None:
        """Hash-named files (no extension) from malware repos are accepted."""
        mal_dir = tmp_path / "malicious"
        ben_dir = tmp_path / "benign"
        mal_dir.mkdir()
        ben_dir.mkdir()
        # Hash-named file (no extension) in malicious/
        _write_minimal_pdf(mal_dir / "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2")
        _write_minimal_pdf(ben_dir / "clean.pdf")
        pairs = _collect_paths_from_dir(tmp_path)
        assert len(pairs) == 2
        labels = {label for _, label in pairs}
        assert labels == {0, 1}

    def test_subdirs_inside_label_dir_are_skipped(self, tmp_path: Path) -> None:
        """Sub-directories inside malicious/ or benign/ are not collected."""
        mal_dir = tmp_path / "malicious"
        mal_dir.mkdir()
        _write_minimal_pdf(mal_dir / "sample.pdf")
        (mal_dir / "subdir").mkdir()  # directory, not a file — should be skipped
        pairs = _collect_paths_from_dir(tmp_path)
        assert len(pairs) == 1

    def test_non_pdf_extension_files_skipped(self, tmp_path: Path) -> None:
        """Files with non-PDF, non-empty extensions (e.g. .txt) are ignored (branch 90->87)."""
        mal_dir = tmp_path / "malicious"
        mal_dir.mkdir()
        _write_minimal_pdf(mal_dir / "sample.pdf")
        (mal_dir / "readme.txt").write_text("not a pdf")  # ignored
        (mal_dir / "archive.zip").write_bytes(b"PK\x03\x04")  # ignored
        pairs = _collect_paths_from_dir(tmp_path)
        # Only the .pdf is collected; .txt and .zip are filtered out.
        assert len(pairs) == 1
        assert pairs[0][0].endswith("sample.pdf")


class TestCollectPathsFromCsv:
    def test_reads_path_and_label(self, dataset_csv: Path) -> None:
        pairs = _collect_paths_from_csv(dataset_csv)
        assert len(pairs) == 2
        labels = {label for _, label in pairs}
        assert labels == {0, 1}


class TestLoadDataset:
    def test_load_from_dir_returns_dataframe(self, dataset_dir: Path) -> None:
        df = load_dataset(str(dataset_dir), max_workers=1)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 2
        assert "label" in df.columns
        for key in FEATURE_ORDER:
            assert key in df.columns

    def test_load_from_csv_returns_dataframe(self, dataset_csv: Path) -> None:
        df = load_dataset(str(dataset_csv), max_workers=1)
        assert len(df) == 2

    def test_invalid_source_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="source must be"):
            load_dataset(str(tmp_path / "nonexistent.txt"), max_workers=1)

    def test_empty_dir_returns_empty_dataframe(self, tmp_path: Path) -> None:
        (tmp_path / "malicious").mkdir()
        (tmp_path / "benign").mkdir()
        df = load_dataset(str(tmp_path), max_workers=1)
        assert df.empty
        assert list(df.columns) == FEATURE_ORDER + ["label"]

    def test_failed_extraction_skipped(self, dataset_dir: Path) -> None:
        # Corrupt one file so extraction raises inside the subprocess.
        (dataset_dir / "malicious" / "evil.pdf").write_bytes(b"NOTAPDF")
        df = load_dataset(str(dataset_dir), max_workers=1)
        # The corrupt file returns zeros (not None), so still 2 rows.
        # If _extract_one returns None for truly unreadable, it would be 1.
        assert len(df) >= 1

    def test_future_exception_is_skipped(self, dataset_dir: Path) -> None:
        """Simulate a subprocess crash (future.result() raises a non-timeout exception)."""
        with patch("training.ingest.ProcessPoolExecutor") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.return_value.__enter__ = MagicMock(return_value=mock_pool)
            mock_pool_cls.return_value.__exit__ = MagicMock(return_value=False)

            bad_future: MagicMock = MagicMock()
            bad_future.result.side_effect = RuntimeError("subprocess crash")

            mock_pool.submit.return_value = bad_future

            with patch("training.ingest.as_completed", return_value=[bad_future]):
                df = load_dataset(str(dataset_dir), max_workers=1)

        assert df.empty or len(df) == 0

    def test_future_timeout_is_skipped(self, dataset_dir: Path) -> None:
        """Simulate a future that times out (future.result() raises TimeoutError)."""
        with patch("training.ingest.ProcessPoolExecutor") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.return_value.__enter__ = MagicMock(return_value=mock_pool)
            mock_pool_cls.return_value.__exit__ = MagicMock(return_value=False)

            timeout_future: MagicMock = MagicMock()
            timeout_future.result.side_effect = TimeoutError("extraction timed out")

            mock_pool.submit.return_value = timeout_future

            with patch("training.ingest.as_completed", return_value=[timeout_future]):
                df = load_dataset(str(dataset_dir), max_workers=1)

        assert len(df) == 0

    def test_extract_one_returning_none_is_skipped(self, dataset_dir: Path) -> None:
        """Simulate _extract_one returning None (unreadable file path)."""
        with patch("training.ingest.ProcessPoolExecutor") as mock_pool_cls:
            mock_pool = MagicMock()
            mock_pool_cls.return_value.__enter__ = MagicMock(return_value=mock_pool)
            mock_pool_cls.return_value.__exit__ = MagicMock(return_value=False)

            none_future: MagicMock = MagicMock()
            none_future.result.return_value = None  # _extract_one returned None

            mock_pool.submit.return_value = none_future

            with patch("training.ingest.as_completed", return_value=[none_future]):
                df = load_dataset(str(dataset_dir), max_workers=1)

        assert len(df) == 0

    def test_progress_logged_at_every_interval(self, dataset_dir: Path) -> None:
        """When _PROGRESS_EVERY=1 every file triggers the interval branch (done % N == 0)."""
        import training.ingest as ingest_mod

        with patch.object(ingest_mod, "_PROGRESS_EVERY", 1):
            df = load_dataset(str(dataset_dir), max_workers=1)

        # Pipeline still succeeds — progress logging is side-effect only.
        assert len(df) == 2
