"""Static probe — extraction and scoring of URI actions in a PDF.

Vector caught: **PDF phishing**. A PDF with a clickable widget/link pointing to
a file-sharing service, a URL with an executable extension, or a bare IP.

Why this probe exists:
  - pdfid does not track `/URI` by default → invisible to pdf_static
  - PDF.js extracts the JS but not the clickable URI actions
  - phishing PDFs often contain no JS at all, just a link

Strategy: regex `/URI (...)` over (1) the raw bytes AND (2) the decompressed
content via `qpdf --qdf`. Many URI actions are in plaintext, but some are hidden
inside FlateDecode streams → invisible to the raw scan alone. Decompression
exposes those hidden URIs (phishing pattern observed on the corpus: a /URI
action inside a compressed object stream).

Scoring heuristic (the MAX wins):
  - URL with executable extension (.exe/.scr/.ps1/etc.) → 0.90
  - bare IP (no DNS, reputation bypass) → 0.70
  - file-sharing service (4sync, mediafire, mega, etc.) → 0.60
  - URL shortener (hides the destination) → 0.50
  - raw content hoster (cdn.discord, raw.githubusercontent, etc.) → 0.40

Signature: (Path) → HypothesisResult — same as the other probes.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from hypotheses._types import Evidence, HypothesisResult

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# Indicator catalogues
# ─────────────────────────────────────────────────────────────────────

# File-sharing services frequently abused (MalwareBazaar corpus)
_FILESHARE_DOMAINS = (
    "4sync.com", "mediafire.com", "mega.nz", "mega.io",
    "wetransfer.com", "anonfiles.com", "transfer.sh",
    "send.cm", "bayfiles.com", "file.io", "ufile.io",
    "easyupload.io", "files.fm", "gofile.io", "krakenfiles.com",
    "uploadrar.com", "uploadhaven.com", "userscloud.com",
    "rapidgator.net", "nitroflare.com", "uploadboy.com",
    "filebin.net", "catbox.moe",
)

# User-content hosters — frequent legitimate use, but abused for payloads.
# Lower score than pure fileshares.
_RAW_HOSTERS = (
    "raw.githubusercontent.com", "pastebin.com",
    "cdn.discordapp.com", "media.discordapp.net",
    "dl.dropboxusercontent.com",
)

# URL shorteners — hide the destination, suspicious by construction
_SHORTENERS = (
    "bit.ly", "t.co", "tinyurl.com", "goo.gl", "ow.ly",
    "is.gd", "buff.ly", "rebrand.ly", "cutt.ly", "shorturl.at",
    "tiny.cc", "lnkd.in", "t.ly", "v.gd",
)

# Free / throwaway hosting (PaaS, static hosting, dynamic-DNS). STRUCTURAL
# category (= "throwaway infra"), not a list of known malware: a PDF
# "invoice/document" pointing to free hosting is a classic phishing pattern
# (ephemeral page, no corporate domain). Same logic as _FILESHARE/_SHORTENERS.
# The user's subdomain precedes these suffixes.
_FREE_HOSTING = (
    "netlify.app", "web.app", "firebaseapp.com", "pages.dev", "workers.dev",
    "glitch.me", "repl.co", "replit.app", "herokuapp.com", "000webhostapp.com",
    "weeblysite.com", "wixsite.com",
    "surge.sh", "vercel.app", "onrender.com", "r2.dev", "blogspot.com",
)
# NB: github.io / gitlab.io REMOVED after calibration (50 benign/100 malic) —
# they massively host LEGITIMATE project pages (e.g. an RFC referencing
# peteroupc.github.io). Malware on github.io falls back to external_url
# (suspicious) → escalated to the LLM, not wrongly classified as malicious.

# Neutral domains / legitimate metadata (XMP, standard schemas). Ignore them
# entirely — their presence is expected in any modern PDF.
_TRUSTED_DOMAINS = (
    "ns.adobe.com", "www.w3.org", "purl.org", "www.aiim.org",
    "schemas.openxmlformats.org", "xmlns.com", "iptc.org",
    "creativecommons.org", "schemas.microsoft.com",
)

# Suspicious TLDs (new generics, frequently abused for phishing).
# Source: Spamhaus/Cisco Talos statistics on TLD abuse 2024-2025.
_SUSPICIOUS_TLDS = (
    "pro", "site", "xyz", "top", "icu", "tk", "ml", "ga", "cf", "gq",
    "work", "click", "win", "rest", "monster", "live", "online", "shop",
    "buzz", "support", "rest", "stream", "loan", "bid", "trade",
)

# Executable / dangerous script extensions in a URL path
_EXEC_EXTS_RE = re.compile(
    r"\.(exe|scr|vbs|ps1|bat|cmd|com|pif|dll|hta|jar|jnlp|js|jse|msi|"
    r"lnk|wsf|wsh|vbe|reg|ade|adp|chm|cpl|ins|isp|mde|sct|shs|"
    r"7z|rar|zip|iso|img|cab|ace)(\?|#|$|/)",
    re.IGNORECASE,
)

# PDF pattern for URI actions: `/URI (https://...)` or `/URI(...)`
# Tolerates spaces, PDF escapes (`\(`, `\)`), max 500 chars of payload.
_URI_RE = re.compile(rb"/URI\s*\(\s*([^)\\][^)]{0,500}?)\s*\)")
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

# Long base64 blob in a URL (query/fragment) — pure OBFUSCATION signal, no list:
# a legitimate URL never embeds 40+ base64 chars in a parameter. Observed
# pattern (fake "download AutoCAD"): evacdir.com/...?QXV0...
_B64_BLOB_RE = re.compile(r"[A-Za-z0-9+/_-]{40,}={0,2}")

_MAX_URIS_SCANNED = 30


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _decompress_qpdf(pdf_path: Path) -> bytes:
    """Decompress the streams via `qpdf --qdf` to expose the /URI actions
    hidden in FlateDecode streams (invisible to the raw-byte regex).

    Returns b'' if qpdf is absent or fails — the probe stays functional on the
    raw bytes (silent degradation).
    """
    try:
        result = subprocess.run(
            ["qpdf", "--qdf", "--object-streams=disable", str(pdf_path), "-"],
            capture_output=True, timeout=15,
        )
        # rc 0 = ok, 2 = warnings: in both cases stdout is usable.
        return result.stdout or b""
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        log.warning("qpdf unavailable/failed — /URI scan limited to raw bytes")
        return b""


def _extract_uris(data: bytes, out: list[str], seen: set[str]) -> None:
    """Extract the http(s)/ftp /URIs from `data`, deduped into `out`/`seen`.

    Caps at _MAX_URIS_SCANNED to avoid a pathological PDF.
    """
    for m in _URI_RE.finditer(data):
        if len(out) >= _MAX_URIS_SCANNED:
            return
        try:
            uri = m.group(1).decode("latin-1", errors="replace").strip()
        except Exception:
            continue
        low = uri.lower()
        if low.startswith(("http://", "https://", "ftp://", "ftps://")) and uri not in seen:
            seen.add(uri)
            out.append(uri)


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

def evaluate_static(pdf_path: Path) -> HypothesisResult:
    """Extract the URI actions and score them by their nature.

    Signature: (Path) → HypothesisResult.
    """
    try:
        data = pdf_path.read_bytes()
    except OSError:
        return HypothesisResult(value=False, score=0.0, evidence=[])

    # URI extraction (capped at _MAX_URIS_SCANNED to avoid pathological cases).
    # 1) raw bytes (plaintext URIs); 2) decompressed content via qpdf
    #    (URIs hidden in FlateDecode streams — otherwise invisible).
    raw_uris: list[str] = []
    seen: set[str] = set()
    _extract_uris(data, raw_uris, seen)
    if len(raw_uris) < _MAX_URIS_SCANNED:
        decompressed = _decompress_qpdf(pdf_path)
        if decompressed:
            _extract_uris(decompressed, raw_uris, seen)

    if not raw_uris:
        return HypothesisResult(value=False, score=0.0, evidence=[])

    score = 0.0
    evidence: list[Evidence] = []

    for uri in raw_uris:
        try:
            parsed = urlparse(uri)
        except ValueError:
            continue
        host = (parsed.hostname or "").lower()
        path = parsed.path or ""
        if not host:
            continue

        # 1. Executable extension in the path — near-certainty of malicious
        if _EXEC_EXTS_RE.search(path):
            score = max(score, 0.9)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_uri.exec_extension",
                value=uri[:200],
            ))
            continue

        # 1-bis. base64 blob in query/fragment = obfuscated URL (behavioural,
        # no list). A legitimate URL does not embed 40+ base64 chars.
        if _B64_BLOB_RE.search((parsed.query or "") + " " + (parsed.fragment or "")):
            score = max(score, 0.6)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_uri.obfuscated_b64_param",
                value=uri[:200],
            ))
            continue

        # 2. Bare IP (no DNS = reputation bypass)
        if _IPV4_RE.match(host):
            score = max(score, 0.7)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_uri.bare_ip",
                value=uri[:200],
            ))
            continue

        # 3. File-sharing service
        if any(host == d or host.endswith("." + d) for d in _FILESHARE_DOMAINS):
            score = max(score, 0.6)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_uri.fileshare",
                value=uri[:200],
            ))
            continue

        # 4. URL shortener
        if host in _SHORTENERS:
            score = max(score, 0.5)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_uri.shortener",
                value=uri[:200],
            ))
            continue

        # 5. Raw content hoster
        if any(host == d or host.endswith("." + d) for d in _RAW_HOSTERS):
            score = max(score, 0.4)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_uri.raw_hoster",
                value=uri[:200],
            ))
            continue

        # 5-bis. Free / throwaway hosting (PaaS, static, dynamic-DNS).
        # Structural category: a document/invoice PDF pointing to throwaway
        # hosting (netlify.app, pages.dev, *.web.app...) = phishing.
        if any(host == d or host.endswith("." + d) for d in _FREE_HOSTING):
            score = max(score, 0.6)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_uri.free_hosting",
                value=uri[:200],
            ))
            continue

        # 6. Trusted domain (XMP metadata, standard schemas) — ignore
        if any(host == d or host.endswith("." + d) for d in _TRUSTED_DOMAINS):
            continue

        # 7. Suspicious TLD — boost
        tld = host.rsplit(".", 1)[-1] if "." in host else ""
        if tld in _SUSPICIOUS_TLDS:
            score = max(score, 0.6)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_uri.suspicious_tld",
                value=f"tld={tld} url={uri[:180]}",
            ))
            continue

        # 8. Fallback: external URL to an uncategorized domain.
        # CALIBRATED (mixed corpus): this fallback fires on 5/7 benigns (an
        # RFC/paper cites 30+ legitimate links) → indistinguishable from phishing
        # to a normal-looking domain WITHOUT a reputation database (excluded by
        # design). We keep it as a WEAK signal (suspicious band, below threshold):
        # present in the evidence for the LLM (which has the email_context), but
        # does not classify as malicious on its own. The discriminating categories
        # (fileshare/exec/IP/shortener/suspicious TLD) keep their strong score above.
        score = max(score, 0.15)
        evidence.append(Evidence(
            source="runtime_signals",
            field_path="pdf_uri.external_url",
            value=uri[:200],
        ))

    return HypothesisResult(
        value=score >= 0.3,
        score=round(score, 3),
        evidence=evidence,
    )
