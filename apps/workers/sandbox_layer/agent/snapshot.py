"""State snapshot avant/après — adapté de GPE-Charon pour tourner DANS le container.

Différence clé vs Charon : on appelle subprocess directement (pas docker exec).
"""

from __future__ import annotations

import shlex
import subprocess

from models import (
    PERSISTENCE_PATHS,
    WATCHED_PATHS,
    FileDiff,
    FileEntry,
    PersistenceEntry,
    ProcessEntry,
    ProcessNode,
    SnapshotDiff,
    SnapshotState,
    SocketEntry,
)


def _run_cmd(args: list[str]) -> str:
    """Exécute une commande sans shell (pas d'interpolation, pas d'injection)."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return result.stdout or ""
    except Exception:
        return ""


def _run_shell(cmd: str) -> str:
    """Exécute un pipeline shell statique. N'appeler qu'avec des chaînes littérales —
    jamais avec des données externes ou des chemins dynamiques non échappés."""
    try:
        result = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True, timeout=30)
        return result.stdout or ""
    except Exception:
        return ""


def take_snapshot(relative_ts_s: float) -> SnapshotState:
    """Capture l'état complet du système local à un instant T."""

    # Filesystem — hashing BATCHÉ (null-delimited).
    # IMPORTANT : l'ancienne version lançait ~1 shell PAR fichier
    # (`xargs -I{} sh -c '...'`) → ~2000 process. Sous la limite CPU du Job +
    # jobs concurrents, ça dépassait par intermittence le timeout de 30s →
    # before-snapshot vide → faux "created" massif → persistence/encryption
    # firaient sur les fichiers système (cron.d, profile.d, terminfo/README).
    # Ici : 2 passes batchées (sha256sum + stat) = ~3× plus rapide et fiable.
    paths_joined = " ".join(shlex.quote(p) for p in WATCHED_PATHS)
    file_list = f"find {paths_joined} -type f -print0 2>/dev/null | head -z -n 4000"

    hashes: dict[str, str] = {}
    hash_out = _run_shell(f"{file_list} | xargs -0 sha256sum 2>/dev/null")
    for line in hash_out.splitlines():
        # format sha256sum : "<hash>  <path>" (deux espaces)
        h, sep, path = line.partition("  ")
        if sep and path:
            hashes[path] = h

    filesystem: list[FileEntry] = []
    # %A = permissions symboliques (ex: -rwxr-xr-x), pour matcher le format
    # documenté de FileEntry.permissions (models.py). %a sortait de l'octal (644)
    # qui ne correspondait pas au contrat du modèle.
    stat_out = _run_shell(f"{file_list} | xargs -0 stat -c '%s|%A|%U|%n' 2>/dev/null")
    for line in stat_out.splitlines():
        parts = line.split("|", 3)
        if len(parts) < 4:
            continue
        size_s, permissions, owner, path = parts
        if not path:
            continue
        try:
            size_bytes = int(size_s)
        except ValueError:
            size_bytes = 0
        filesystem.append(FileEntry(
            path=path, sha256=hashes.get(path),
            size_bytes=size_bytes, permissions=permissions, owner=owner,
            mtime_relative_s=relative_ts_s,
        ))

    # Process tree
    # args en dernière colonne → contient des espaces, donc split(None, 5) le
    # garde entier. Avant ce fix, le format s'arrêtait à `stat` et cmdline était
    # rempli avec la valeur STAT (Ss, R+, …) au lieu de la vraie ligne de commande.
    ps_out = _run_cmd(["ps", "axo", "pid,ppid,user,comm,stat,args", "--no-headers"])
    process_tree: list[ProcessNode] = []
    for line in ps_out.splitlines():
        parts = line.split(None, 5)
        if len(parts) < 5:           # pid ppid user comm stat = minimum requis
            continue
        try:
            entry = ProcessEntry(
                pid=int(parts[0]), ppid=int(parts[1]),
                user=parts[2], comm=parts[3][:15],
                stat=parts[4],
                # args vide pour les threads noyau / zombies → cmdline ""
                cmdline=(parts[5][:512] if len(parts) == 6 else ""),
            )
            process_tree.append(ProcessNode(entry=entry))
        except (ValueError, IndexError):
            continue

    # Sockets
    sockets: list[SocketEntry] = []
    for line in _run_cmd(["ss", "-tulnp"]).splitlines()[1:]:
        parts = line.split()
        if len(parts) < 5:
            continue
        proto_raw = parts[0].lower()
        if proto_raw not in ("tcp", "tcp6", "udp", "udp6"):
            continue
        local = parts[4]
        if ":" in local:
            addr, _, port_s = local.rpartition(":")
            try:
                sockets.append(SocketEntry(
                    proto=proto_raw, local_addr=addr or "0.0.0.0",
                    local_port=int(port_s), state=parts[1],
                ))
            except (ValueError, IndexError):
                continue

    # Crontab — deux appels séparés sans shell pour éviter l'injection
    crontab_out = _run_cmd(["crontab", "-l"]) + _run_shell("cat /etc/cron* 2>/dev/null")
    crontab_lines = [l for l in crontab_out.splitlines() if l.strip() and not l.startswith("#")]

    # Systemd — pipeline statique, _run_shell acceptable ici
    systemd_out = _run_shell(
        "systemctl list-units --state=active --no-legend --no-pager 2>/dev/null | awk '{print $1}'"
    )
    systemd_units = [l.strip() for l in systemd_out.splitlines() if l.strip()]

    # Persistance — shlex.quote sur chaque chemin pour éviter l'injection
    persist_cmd = "; ".join(f"sha256sum {shlex.quote(p)} 2>/dev/null" for p in PERSISTENCE_PATHS)
    persistence_entries: list[PersistenceEntry] = []
    for line in _run_shell(persist_cmd).splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            persistence_entries.append(PersistenceEntry(path=parts[1], content_sha256=parts[0]))

    return SnapshotState(
        captured_at_relative_s=relative_ts_s,
        filesystem=filesystem,
        process_tree=process_tree,
        sockets=sockets,
        crontab_lines=crontab_lines,
        systemd_active_units=systemd_units,
        persistence_entries=persistence_entries,
    )


def compute_diff(
    before: SnapshotState,
    after: SnapshotState,
    execution_duration_s: float,
    exit_code: int | None = None,
) -> SnapshotDiff:
    before_fs = {f.path: f for f in before.filesystem}
    after_fs  = {f.path: f for f in after.filesystem}

    # Garde-fou : si le before-snapshot est vide mais l'after est substantiel,
    # le snapshot d'avant a échoué (timeout/erreur) — NE PAS conclure que tout a
    # été "créé" (sinon faux persistence/encryption massifs). On neutralise alors
    # le diff fichiers (les autres signaux — réseau, process — restent valides).
    _fs_unreliable = (not before_fs) and (len(after_fs) > 20)

    file_diffs: list[FileDiff] = []
    if _fs_unreliable:
        before_fs = after_fs  # diff fichiers neutralisé : aucun "created/modified/deleted"
    for path, f in after_fs.items():
        if path not in before_fs:
            file_diffs.append(FileDiff(path=path, kind="created",
                                       sha256_after=f.sha256, size_delta_bytes=f.size_bytes))
    for path, f_before in before_fs.items():
        if path in after_fs:
            f_after = after_fs[path]
            if f_before.sha256 != f_after.sha256:
                file_diffs.append(FileDiff(
                    path=path, kind="modified",
                    sha256_before=f_before.sha256, sha256_after=f_after.sha256,
                    size_delta_bytes=f_after.size_bytes - f_before.size_bytes,
                ))
    for path, f in before_fs.items():
        if path not in after_fs:
            file_diffs.append(FileDiff(path=path, kind="deleted",
                                       sha256_before=f.sha256, size_delta_bytes=-f.size_bytes))

    before_pids = {n.entry.pid: n.entry for n in before.process_tree}
    after_pids  = {n.entry.pid: n.entry for n in after.process_tree}

    before_sockets = {(s.proto, s.local_addr, s.local_port) for s in before.sockets}
    after_sockets_map = {(s.proto, s.local_addr, s.local_port): s for s in after.sockets}

    before_cron = set(before.crontab_lines)
    after_cron  = set(after.crontab_lines)

    before_persist = {p.path: p for p in before.persistence_entries}
    after_persist  = {p.path: p for p in after.persistence_entries}

    return SnapshotDiff(
        execution_duration_s=execution_duration_s,
        file_diffs=file_diffs,
        files_created_count=sum(1 for d in file_diffs if d.kind == "created"),
        files_modified_count=sum(1 for d in file_diffs if d.kind == "modified"),
        files_deleted_count=sum(1 for d in file_diffs if d.kind == "deleted"),
        processes_spawned=[e for pid, e in after_pids.items() if pid not in before_pids],
        processes_terminated=[e for pid, e in before_pids.items() if pid not in after_pids],
        sockets_opened=[s for k, s in after_sockets_map.items() if k not in before_sockets],
        sockets_closed=[s for s in before.sockets
                        if (s.proto, s.local_addr, s.local_port) not in after_sockets_map],
        crontab_additions=list(after_cron - before_cron),
        crontab_deletions=list(before_cron - after_cron),
        systemd_additions=[u for u in after.systemd_active_units if u not in before.systemd_active_units],
        persistence_changes=[
            p for path, p in after_persist.items()
            if path not in before_persist or before_persist[path].content_sha256 != p.content_sha256
        ],
        exit_code=exit_code,
    )
