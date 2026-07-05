"""Fetch benign PDFs from arXiv to diversify the ML layer's benign corpus.

arXiv is a moderated source, so its PDFs can be trusted as benign; arbitrary web
PDFs must never be scraped into the benign label because they may be malware. It
also supplies multi-page documents from many producers, the exact benign class
modern malware mimics. Files are saved as ``arxiv_<id>.pdf`` and re-runs skip
what is already on disk.
"""

from __future__ import annotations

import argparse
import logging
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_API_URL = "http://export.arxiv.org/api/query"
_ATOM = "{http://www.w3.org/2005/Atom}"
_PDF_MAGIC = b"%PDF-"
_HTTP_TIMEOUT_S = 60.0
_ERROR_PREVIEW_BYTES = 60

DEFAULT_CATEGORIES = ["q-fin.GN", "econ.GN", "cs.CR", "eess.SY", "stat.AP"]


# arXiv wants raw '+OR+' operators in the query; httpx's params encoder would
# percent-escape them into an invalid query, so the URL is built literally.
def _build_query_url(categories: list[str], start: int, max_results: int) -> str:
    query = "+OR+".join(f"cat:{c}" for c in categories)
    return (
        f"{_API_URL}?search_query={query}"
        f"&start={start}&max_results={max_results}"
        "&sortBy=lastUpdatedDate&sortOrder=descending"
    )


def list_recent_ids(
    client: httpx.Client, categories: list[str], max_results: int, start: int = 0
) -> list[str]:
    resp = client.get(_build_query_url(categories, start, max_results))
    root = ET.fromstring(resp.text)
    ids: list[str] = []
    for entry in root.findall(f"{_ATOM}entry"):
        id_el = entry.find(f"{_ATOM}id")
        if id_el is not None and id_el.text:
            ids.append(id_el.text.rsplit("/abs/", 1)[-1])
    return ids


def download_pdf(client: httpx.Client, arxiv_id: str) -> bytes | None:
    resp = client.get(f"https://arxiv.org/pdf/{arxiv_id}")
    content = resp.content
    if content[: len(_PDF_MAGIC)] != _PDF_MAGIC:
        logger.warning("Not a PDF for %s (got %s)", arxiv_id, content[:_ERROR_PREVIEW_BYTES])
        return None
    return content


def fetch(
    out_dir: str,
    categories: list[str] | None = None,
    limit: int = 200,
    sleep: float = 1.0,
    client: httpx.Client | None = None,
) -> dict[str, int]:
    categories = categories or DEFAULT_CATEGORIES
    own_client = client is None
    client = client or httpx.Client(timeout=_HTTP_TIMEOUT_S, follow_redirects=True)
    try:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        ids = list_recent_ids(client, categories, limit)
        logger.info("arXiv returned %d IDs -> %s", len(ids), out)

        written = skipped = failed = 0
        for arxiv_id in ids:
            dest = out / f"arxiv_{arxiv_id.replace('/', '_')}.pdf"
            if dest.exists():
                skipped += 1
                continue
            pdf = download_pdf(client, arxiv_id)
            if pdf is None:
                failed += 1
                continue
            dest.write_bytes(pdf)
            written += 1
            if sleep:
                time.sleep(sleep)

        logger.info("Done: %d written, %d already present, %d failed", written, skipped, failed)
        return {"written": written, "skipped": skipped, "failed": failed}
    finally:
        if own_client:
            client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch benign PDFs from arXiv")
    parser.add_argument("--out", default="data/benign", help="Destination directory")
    parser.add_argument("--limit", type=int, default=200, help="Max PDFs to fetch")
    parser.add_argument("--sleep", type=float, default=1.0, help="Seconds between downloads")
    parser.add_argument(
        "--categories",
        default=",".join(DEFAULT_CATEGORIES),
        help="Comma-separated arXiv categories",
    )
    args = parser.parse_args()
    fetch(
        args.out,
        categories=[c.strip() for c in args.categories.split(",") if c.strip()],
        limit=args.limit,
        sleep=args.sleep,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
