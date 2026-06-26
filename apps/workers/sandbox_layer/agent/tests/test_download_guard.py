"""SSRF guard on the ELF sample download: only http/https to an allowlisted host."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

import run_analysis


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "gopher://127.0.0.1:6379/_",
    "http://169.254.169.254/latest/meta-data/",
    "https://evil.example.com/x.elf",
])
def test_download_rejects_disallowed_url(url, tmp_path):
    with pytest.raises(ValueError):
        run_analysis._download_sample(url, tmp_path / "sample.elf")


def test_allowlisted_host_passes_the_guard(monkeypatch, tmp_path):
    # Host is allowed → guard passes; fail only at the network call, never at validation.
    allowed = sorted(run_analysis.ALLOWED_DOWNLOAD_HOSTS)[0]
    raised = {}

    def _boom(*a, **k):
        raised["called"] = True
        raise OSError("network disabled in test")

    monkeypatch.setattr(run_analysis.urllib.request, "urlopen", _boom)
    with pytest.raises(OSError):
        run_analysis._download_sample(f"http://{allowed}/sample.elf", tmp_path / "sample.elf")
    assert raised["called"]
