"""Memory forensics via /proc — runs INSIDE the container (not docker exec).
Adapted from GPE-Charon/sandbox/memory/procfs_memory.py.
"""

from __future__ import annotations

import json
import logging
import os
import re

from models import MAX_DECODED_STRINGS, MemoryObservables, MemoryRegion, PslistEntry

logger = logging.getLogger(__name__)

_STRING_RE = re.compile(rb"[ -~]{6,}")
_MAX_REGION_BYTES = 64 * 1024 * 1024


def _read_ppid(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("PPid:"):
                    return int(line.split()[1])
    except OSError:
        pass
    return 0


def _read_proc_entry(pid: int) -> PslistEntry | None:
    try:
        comm = open(f"/proc/{pid}/comm").read().strip()
        return PslistEntry(pid=pid, ppid=_read_ppid(pid), comm=comm)
    except OSError:
        return None


def _pslist() -> list[PslistEntry]:
    pids = (int(d) for d in os.listdir("/proc") if d.isdigit())
    return [entry for pid in pids if (entry := _read_proc_entry(pid)) is not None]


def _parse_maps(pid: int) -> list[dict]:
    regions = []
    try:
        with open(f"/proc/{pid}/maps") as f:
            for line in f:
                p = line.split(None, 5)
                if len(p) < 5:
                    continue
                start_hex, end_hex = p[0].split("-")
                regions.append({
                    "start": int(start_hex, 16),
                    "end": int(end_hex, 16),
                    "perms": p[1],
                })
    except OSError:
        pass
    return regions


def _read_region(pid: int, start: int, size: int) -> bytes:
    try:
        with open(f"/proc/{pid}/mem", "rb") as f:
            f.seek(start)
            return f.read(min(size, _MAX_REGION_BYTES))
    except OSError:
        return b""


def _find_sample_pid(sample_path: str) -> int | None:
    """Find the PID whose exe is sample_path."""
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            if os.readlink(f"/proc/{d}/exe") == sample_path:
                return int(d)
        except OSError:
            continue
    return None


def collect_memory_observables(
    sample_path: str,
    *,
    max_snapshots: int = 5,
    interval_s: float = 0.5,
) -> MemoryObservables:
    """Collect memory observables by reading /proc directly."""
    import time

    suspicious_by_addr: dict[tuple[int, str], MemoryRegion] = {}
    strings_set: set[str] = set()
    pslist_last: list[PslistEntry] = []

    for tick in range(max_snapshots):
        time.sleep(interval_s)

        pid = _find_sample_pid(sample_path)
        if pid is None:
            logger.info("Memory tick %d: sample not running", tick)
            continue

        try:
            comm = open(f"/proc/{pid}/comm").read().strip()
        except OSError:
            comm = ""

        regions = _parse_maps(pid)
        for r in regions:
            if "r" in r["perms"] and "w" in r["perms"] and "x" in r["perms"]:
                size = r["end"] - r["start"]
                key = (pid, hex(r["start"]))
                suspicious_by_addr[key] = MemoryRegion(
                    pid=pid, comm=comm,
                    start_addr=hex(r["start"]), end_addr=hex(r["end"]),
                    permissions=r["perms"], size_bytes=size,
                )
                data = _read_region(pid, r["start"], size)
                for m in _STRING_RE.finditer(data):
                    s = m.group().decode("ascii", errors="replace")[:128]
                    if len(strings_set) < MAX_DECODED_STRINGS:
                        strings_set.add(s)

        pslist_last = _pslist()
        logger.info("Memory tick %d: pid=%d rwx=%d strings=%d",
                    tick, pid, len(suspicious_by_addr), len(strings_set))

    return MemoryObservables(
        pslist=pslist_last,
        hidden_pids=[],
        suspicious_regions=list(suspicious_by_addr.values()),
        decoded_strings=sorted(strings_set)[:MAX_DECODED_STRINGS],
    )
