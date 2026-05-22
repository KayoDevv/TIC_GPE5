"""Sonde statique — extraction et scoring des actions URI dans un PDF.

Vecteur catché : **phishing PDF**. Un PDF avec un widget/lien cliquable qui
pointe vers un service de partage de fichiers, une URL avec extension
exécutable, ou une IP nue.

Pourquoi cette sonde existe :
  - pdfid ne track pas `/URI` par défaut → invisible à pdf_static
  - PDF.js extrait le JS mais pas les actions URI cliquables
  - Les phishing PDFs ne contiennent souvent aucun JS, juste un lien

Stratégie : regex `/URI (...)` sur (1) les octets bruts ET (2) le contenu
décompressé via `qpdf --qdf`. Beaucoup d'actions URI sont en plaintext, mais
certaines sont planquées dans des streams FlateDecode → invisibles au scan
brut seul. La décompression expose ces URIs cachés (pattern phishing observé
sur le corpus : action /URI dans un object stream compressé).

Heuristique de scoring (le MAX gagne) :
  - URL avec extension exécutable (.exe/.scr/.ps1/etc.) → 0.90
  - IP nue (pas de DNS, contournement reputation) → 0.70
  - Service de partage de fichiers (4sync, mediafire, mega, etc.) → 0.60
  - URL shortener (masque la destination) → 0.50
  - Raw content hoster (cdn.discord, raw.githubusercontent, etc.) → 0.40

Signature: (Path) → HypothesisResult — identique aux autres sondes.
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
# Catalogues d'indicateurs
# ─────────────────────────────────────────────────────────────────────

# Services de partage de fichiers fréquemment abusés (corpus MalwareBazaar)
_FILESHARE_DOMAINS = (
    "4sync.com", "mediafire.com", "mega.nz", "mega.io",
    "wetransfer.com", "anonfiles.com", "transfer.sh",
    "send.cm", "bayfiles.com", "file.io", "ufile.io",
    "easyupload.io", "files.fm", "gofile.io", "krakenfiles.com",
    "uploadrar.com", "uploadhaven.com", "userscloud.com",
    "rapidgator.net", "nitroflare.com", "uploadboy.com",
    "filebin.net", "catbox.moe",
)

# Hébergeurs de contenu utilisateur — usage légit fréquent, mais abusé pour
# payloads. Score plus faible que les fileshares purs.
_RAW_HOSTERS = (
    "raw.githubusercontent.com", "pastebin.com",
    "cdn.discordapp.com", "media.discordapp.net",
    "dl.dropboxusercontent.com",
)

# URL shorteners — masquent la destination, suspect par construction
_SHORTENERS = (
    "bit.ly", "t.co", "tinyurl.com", "goo.gl", "ow.ly",
    "is.gd", "buff.ly", "rebrand.ly", "cutt.ly", "shorturl.at",
    "tiny.cc", "lnkd.in", "t.ly", "v.gd",
)

# Hébergement gratuit / jetable (PaaS, static hosting, dynamic-DNS). Catégorie
# STRUCTURELLE (= "infra throwaway"), pas une liste de malwares connus : un PDF
# "facture/document" pointant vers du free-hosting est un pattern phishing
# classique (page éphémère, pas de domaine d'entreprise). Même logique que
# _FILESHARE/_SHORTENERS. Le sous-domaine de l'utilisateur précède ces suffixes.
_FREE_HOSTING = (
    "netlify.app", "web.app", "firebaseapp.com", "pages.dev", "workers.dev",
    "glitch.me", "repl.co", "replit.app", "herokuapp.com", "000webhostapp.com",
    "weeblysite.com", "wixsite.com",
    "surge.sh", "vercel.app", "onrender.com", "r2.dev", "blogspot.com",
)
# NB : github.io / gitlab.io RETIRÉS après calibration (50 benign/100 malic) —
# ils hébergent massivement des pages de projet LÉGITIMES (ex. RFC référençant
# peteroupc.github.io). Un malware sur github.io retombe sur external_url
# (suspicious) → escaladé au LLM, pas classé malicious à tort.

# Domaines neutres / metadata légitime (XMP, schémas standards). À ignorer
# complètement — leur présence est attendue dans tout PDF moderne.
_TRUSTED_DOMAINS = (
    "ns.adobe.com", "www.w3.org", "purl.org", "www.aiim.org",
    "schemas.openxmlformats.org", "xmlns.com", "iptc.org",
    "creativecommons.org", "schemas.microsoft.com",
)

# TLDs suspects (génériques nouveaux, fréquemment abusés pour phishing).
# Source : statistiques Spamhaus/Cisco Talos sur abus TLDs 2024-2025.
_SUSPICIOUS_TLDS = (
    "pro", "site", "xyz", "top", "icu", "tk", "ml", "ga", "cf", "gq",
    "work", "click", "win", "rest", "monster", "live", "online", "shop",
    "buzz", "support", "rest", "stream", "loan", "bid", "trade",
)

# Extensions exécutables / scripts dangereux dans le path d'une URL
_EXEC_EXTS_RE = re.compile(
    r"\.(exe|scr|vbs|ps1|bat|cmd|com|pif|dll|hta|jar|jnlp|js|jse|msi|"
    r"lnk|wsf|wsh|vbe|reg|ade|adp|chm|cpl|ins|isp|mde|sct|shs|"
    r"7z|rar|zip|iso|img|cab|ace)(\?|#|$|/)",
    re.IGNORECASE,
)

# Pattern PDF pour les actions URI : `/URI (https://...)` ou `/URI(...)`
# Tolère des espaces, échappements PDF (`\(`, `\)`), max 500 chars de payload.
_URI_RE = re.compile(rb"/URI\s*\(\s*([^)\\][^)]{0,500}?)\s*\)")
_IPV4_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

# Blob base64 long dans une URL (query/fragment) — signal d'OBFUSCATION pur,
# aucune liste : une URL légitime n'embarque jamais 40+ chars base64 en
# paramètre. Pattern observé (faux "download AutoCAD") : evacdir.com/...?QXV0...
_B64_BLOB_RE = re.compile(r"[A-Za-z0-9+/_-]{40,}={0,2}")

_MAX_URIS_SCANNED = 30


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _decompress_qpdf(pdf_path: Path) -> bytes:
    """Décompresse les streams via `qpdf --qdf` pour exposer les actions /URI
    cachées dans des streams FlateDecode (invisibles au regex sur octets bruts).

    Retourne b'' si qpdf est absent ou échoue — la sonde reste fonctionnelle
    sur les octets bruts (dégradation silencieuse).
    """
    try:
        result = subprocess.run(
            ["qpdf", "--qdf", "--object-streams=disable", str(pdf_path), "-"],
            capture_output=True, timeout=15,
        )
        # rc 0 = ok, 2 = warnings : dans les deux cas stdout est exploitable.
        return result.stdout or b""
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        log.warning("qpdf unavailable/failed — /URI scan limited to raw bytes")
        return b""


def _extract_uris(data: bytes, out: list[str], seen: set[str]) -> None:
    """Extrait les /URI http(s)/ftp de `data`, dédupliqué dans `out`/`seen`.

    Cappe à _MAX_URIS_SCANNED pour éviter un PDF pathologique.
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
    """Extrait les actions URI et score selon leur nature.

    Signature: (Path) → HypothesisResult.
    """
    try:
        data = pdf_path.read_bytes()
    except OSError:
        return HypothesisResult(value=False, score=0.0, evidence=[])

    # Extraction des URIs (cap à _MAX_URIS_SCANNED pour éviter pathological).
    # 1) octets bruts (URIs en plaintext) ; 2) contenu décompressé via qpdf
    #    (URIs cachés dans des streams FlateDecode — sinon invisibles).
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

        # 1. Extension exécutable dans le path — quasi-certitude de malicious
        if _EXEC_EXTS_RE.search(path):
            score = max(score, 0.9)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_uri.exec_extension",
                value=uri[:200],
            ))
            continue

        # 1-bis. Blob base64 dans query/fragment = URL obfusquée (comportemental,
        # pas de liste). Une URL légitime n'embarque pas 40+ chars base64.
        if _B64_BLOB_RE.search((parsed.query or "") + " " + (parsed.fragment or "")):
            score = max(score, 0.6)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_uri.obfuscated_b64_param",
                value=uri[:200],
            ))
            continue

        # 2. IP nue (pas de DNS = contournement reputation)
        if _IPV4_RE.match(host):
            score = max(score, 0.7)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_uri.bare_ip",
                value=uri[:200],
            ))
            continue

        # 3. Service de partage de fichiers
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

        # 5. Hébergeur raw content
        if any(host == d or host.endswith("." + d) for d in _RAW_HOSTERS):
            score = max(score, 0.4)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_uri.raw_hoster",
                value=uri[:200],
            ))
            continue

        # 5-bis. Hébergement gratuit / jetable (PaaS, static, dynamic-DNS).
        # Catégorie structurelle : un PDF document/facture pointant vers du
        # throwaway hosting (netlify.app, pages.dev, *.web.app...) = phishing.
        if any(host == d or host.endswith("." + d) for d in _FREE_HOSTING):
            score = max(score, 0.6)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_uri.free_hosting",
                value=uri[:200],
            ))
            continue

        # 6. Domaine trusted (XMP metadata, schémas standards) — ignorer
        if any(host == d or host.endswith("." + d) for d in _TRUSTED_DOMAINS):
            continue

        # 7. TLD suspect — boost
        tld = host.rsplit(".", 1)[-1] if "." in host else ""
        if tld in _SUSPICIOUS_TLDS:
            score = max(score, 0.6)
            evidence.append(Evidence(
                source="runtime_signals",
                field_path="pdf_uri.suspicious_tld",
                value=f"tld={tld} url={uri[:180]}",
            ))
            continue

        # 8. Fallback : URL externe vers un domaine non catégorisé.
        # CALIBRÉ (corpus mixte) : ce fallback fire sur 5/7 benigns (un RFC/papier
        # cite 30+ liens légitimes) → indiscernable d'un phishing vers un domaine
        # d'apparence normale SANS base de réputation (exclue par design). On le
        # garde en signal FAIBLE (bande suspicious, sous le seuil) : présent dans
        # l'evidence pour le LLM (qui a l'email_context), mais ne classe pas seul
        # en malicious. Les catégories discriminantes (fileshare/exec/IP/shortener/
        # TLD suspect) gardent leur score fort au-dessus.
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
