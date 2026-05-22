"""Modèles de données intermédiaires — contrat central du pipeline sandbox Linux.

Ce fichier est la **source de vérité** pour tous les types échangés entre :
    - le backend linux_docker (collecte)
    - les 6 hypothèses (Couche 2)
    - le memory runner /proc forensics (Couche 3)
    - le report builder (Couche 4)

Principes de design (issus du brainstorm expert-council) :
    - Tous les modèles sont **frozen** (immutables après création).
    - Les timestamps sont **relatifs à t=0 (début d'exécution)**, jamais absolus.
    - Aucun raw bytes embarqué (sécurité + volumétrie).
    - Strings tronquées avant ingestion (anti-injection prompt LLM).
    - Syscalls : agrégés (SyscallSummary), pas raw (millions d'events possibles).
    - inotify : cappé à MAX_INOTIFY_EVENTS (ransomware peut en générer des millions).
    - Filesystem surveillé : /etc /home /tmp /var /opt /root uniquement.

Hiérarchie des modèles :

    SnapshotState  (avant)  ─┐
                              ├──► SnapshotDiff ──┐
    SnapshotState  (après)  ─┘                    ├──► HypothesisResult (× 6)
    RuntimeSignals ───────────────────────────────┤
    MemoryObservables ────────────────────────────┘

    HypothesisResult × 6 ──► AnomalyScore ──► report/builder.py

Stack de collecte :
    - strace -f -tt -e trace=all  → SyscallSummary  (remplace eBPF)
    - /proc/[pid]/maps + /proc/[pid]/mem + SIGSTOP  → MemoryObservables
    - Docker + seccomp whitelist + --cap-drop ALL  (remplace gVisor)
    - K3s in-cluster : Bitnami Kafka + MinIO StatefulSet (ns kafka, minio)
      + consumer/watcher/Jobs (ns sandbox)

Usage:
    from backends.linux_docker.models import SnapshotDiff, RuntimeSignals, MemoryObservables
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Constantes de sécurité / volumétrie
# ---------------------------------------------------------------------------

MAX_INOTIFY_EVENTS: int = 10_000
MAX_CMDLINE_CHARS: int = 512
MAX_DECODED_STRING_CHARS: int = 128
MAX_DECODED_STRINGS: int = 500
MAX_SYSCALL_SAMPLE_ARGS: int = 20
MAX_SYSCALL_ARG_CHARS: int = 256

# Chemins filesystem surveillés (hors /usr /lib /bin → trop statiques)
WATCHED_PATHS: tuple[str, ...] = (
    "/etc",
    "/home",
    "/tmp",
    "/var",
    "/opt",
    "/root",
)

# Chemins de persistance connus
PERSISTENCE_PATHS: tuple[str, ...] = (
    "/etc/cron.d",
    "/etc/crontab",
    "/etc/profile.d",
    "/etc/rc.local",
    "/etc/init.d",
    "/root/.ssh/authorized_keys",
    "/root/.bashrc",
    "/root/.profile",
)


# ---------------------------------------------------------------------------
# Couche 1 — Primitives partagées
# ---------------------------------------------------------------------------


class FileEntry(BaseModel):
    """Fichier observé à un instant T.

    sha256 est None si le fichier n'est pas lisible (permissions, socket, etc.).
    mtime_relative_s est relatif au démarrage de l'exécution (t=0).
    """

    model_config = ConfigDict(frozen=True)

    path: str
    sha256: str | None = None
    size_bytes: int
    permissions: str  # symbolique (sortie stat %A), ex: "-rwxr-xr-x"
    owner: str  # ex: "root" ou "user"
    mtime_relative_s: float  # secondes depuis t=0


class ProcessEntry(BaseModel):
    """Entrée de process (depuis ps auxf ou /proc).

    cmdline tronqué à MAX_CMDLINE_CHARS avant stockage.
    ld_preload extrait uniquement de /proc/[pid]/environ (pas l'env complet).
    """

    model_config = ConfigDict(frozen=True)

    pid: int
    ppid: int
    user: str
    comm: str  # nom court (15 chars max, champ COMM de ps)
    cmdline: Annotated[str, Field(max_length=MAX_CMDLINE_CHARS)]
    stat: str  # R/S/D/Z/T
    ld_preload: str | None = None  # valeur de LD_PRELOAD si présente


class ProcessNode(BaseModel):
    """Nœud d'arbre process — hiérarchie parent/enfant.

    Appeler ProcessNode.model_rebuild() après définition de la classe
    pour résoudre la référence forward.
    """

    model_config = ConfigDict(frozen=True)

    entry: ProcessEntry
    children: list[ProcessNode] = Field(default_factory=list)


ProcessNode.model_rebuild()


class SocketEntry(BaseModel):
    """Socket réseau ouvert (depuis ss --json).

    remote_addr / remote_port sont None pour les sockets en LISTEN.
    pid est None si l'association process→socket n'a pas pu être résolue.
    """

    model_config = ConfigDict(frozen=True)

    proto: Literal["tcp", "tcp6", "udp", "udp6"]
    local_addr: str
    local_port: int
    remote_addr: str | None = None
    remote_port: int | None = None
    state: str  # ESTABLISHED, LISTEN, TIME_WAIT, etc.
    pid: int | None = None


class PersistenceEntry(BaseModel):
    """Chemin de persistance connu + empreinte de son contenu.

    Surveille : cron.d, profile.d, authorized_keys, rc.local, init.d, bashrc.
    content_sha256 permet de détecter toute modification entre avant/après.
    """

    model_config = ConfigDict(frozen=True)

    path: str
    content_sha256: str  # SHA-256 du contenu du fichier


# ---------------------------------------------------------------------------
# Couche 2 — SnapshotState (état du système à un instant T)
# ---------------------------------------------------------------------------


class SnapshotState(BaseModel):
    """Photographie complète de l'état système à un instant T.

    captured_at_relative_s = 0.0 pour le snapshot AVANT exécution.
    captured_at_relative_s > 0 pour le snapshot APRÈS exécution.

    filesystem : uniquement les chemins sous WATCHED_PATHS.
    process_tree : arbre hiérarchique complet (tous les process visibles via ps).
    persistence_entries : uniquement les chemins de PERSISTENCE_PATHS existants.
    """

    model_config = ConfigDict(frozen=True)

    captured_at_relative_s: float
    filesystem: list[FileEntry]
    process_tree: list[ProcessNode]
    sockets: list[SocketEntry]
    crontab_lines: list[str]
    systemd_active_units: list[str]
    persistence_entries: list[PersistenceEntry]


# ---------------------------------------------------------------------------
# Couche 3 — SnapshotDiff (différentiel avant → après)
# ---------------------------------------------------------------------------


class FileDiff(BaseModel):
    """Changement de fichier entre snapshot avant et snapshot après.

    kind:
        created  — fichier absent avant, présent après
        modified — sha256 différent entre avant et après
        deleted  — fichier présent avant, absent après
    """

    model_config = ConfigDict(frozen=True)

    path: str
    kind: Literal["created", "modified", "deleted"]
    sha256_before: str | None = None
    sha256_after: str | None = None
    size_delta_bytes: int = 0
    permissions_before: str | None = None
    permissions_after: str | None = None


class SnapshotDiff(BaseModel):
    """Différentiel calculé entre SnapshotState avant et SnapshotState après.

    C'est l'INPUT PRINCIPAL des 6 hypothèses (Couche 2).
    Immutable — calculé une seule fois par analyse, partagé entre tous les modules.

    files_created_count / files_deleted_count : dénombrements rapides utilisés
    par hypothesis_encryption pour détecter un renommage massif en masse.
    """

    model_config = ConfigDict(frozen=True)

    execution_duration_s: float

    # --- Filesystem ---
    file_diffs: list[FileDiff]
    files_created_count: int  # len([d for d in file_diffs if d.kind == "created"])
    files_modified_count: int
    files_deleted_count: int

    # --- Processes ---
    processes_spawned: list[ProcessEntry]  # dans after, absents dans before
    processes_terminated: list[ProcessEntry]  # dans before, absents dans after

    # --- Sockets ---
    sockets_opened: list[SocketEntry]  # dans after, absents dans before
    sockets_closed: list[SocketEntry]  # dans before, absents dans after

    # --- Persistance ---
    crontab_additions: list[str]  # lignes ajoutées
    crontab_deletions: list[str]  # lignes supprimées
    systemd_additions: list[str]  # nouvelles units actives
    persistence_changes: list[PersistenceEntry]  # entrées créées ou modifiées

    # --- Métadonnées d'exécution ---
    exit_code: int | None = None


# ---------------------------------------------------------------------------
# Couche 4 — RuntimeSignals (collecte PENDANT l'exécution)
# ---------------------------------------------------------------------------


class SyscallSummary(BaseModel):
    """Résumé agrégé d'un syscall — pas de raw events (trop volumineux).

    Collecté via strace -f -tt -e trace=all (SYS_PTRACE cap requis).
    sample_args : les 3 premières occurrences des arguments, tronquées.
    Exemples de syscalls intéressants : openat, connect, clone, ptrace,
    execve, mmap, mprotect, write, unlink.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    call_count: int
    unique_pids: list[int]
    sample_args: Annotated[
        list[Annotated[str, Field(max_length=MAX_SYSCALL_ARG_CHARS)]],
        Field(max_length=MAX_SYSCALL_SAMPLE_ARGS),
    ] = Field(default_factory=list)


class InotifyEvent(BaseModel):
    """Événement inotify horodaté (relatif à t=0).

    Collecté via inotifywait -m -r sur WATCHED_PATHS.
    La liste totale est cappée à MAX_INOTIFY_EVENTS dans RuntimeSignals.
    """

    model_config = ConfigDict(frozen=True)

    relative_ts_s: float
    kind: Literal["CREATE", "MODIFY", "DELETE", "MOVED_FROM", "MOVED_TO", "ATTRIB"]
    path: str
    filename: str


class DnsQuery(BaseModel):
    """Requête DNS capturée via INetSim (fake DNS resolver).

    answers : adresses IP retournées (INetSim retourne toujours une IP factice).
    """

    model_config = ConfigDict(frozen=True)

    query: str
    qtype: str  # A, AAAA, MX, TXT, CNAME, ...
    answers: list[str]
    relative_ts_s: float


class HttpRequest(BaseModel):
    """Requête HTTP/S capturée via INetSim.

    response_code : None si la connexion a été coupée avant la réponse.
    """

    model_config = ConfigDict(frozen=True)

    method: str
    host: str
    uri: str
    user_agent: str | None = None
    response_code: int | None = None
    relative_ts_s: float


class NetworkFlow(BaseModel):
    """Flux TCP ou UDP — agrégé par 5-tuple depuis le PCAP.

    bytes_sent et packet_count sont du point de vue du sample (src = container).
    """

    model_config = ConfigDict(frozen=True)

    proto: Literal["tcp", "udp"]
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    bytes_sent: int
    packet_count: int
    first_seen_relative_s: float


class NetworkObservables(BaseModel):
    """Tous les observables réseau collectés pendant l'exécution.

    Structure inspirée de Cuckoo network section (seule partie portable de Cuckoo).
    dns_queries et http_requests viennent de INetSim.
    tcp_flows et udp_flows viennent du PCAP (tcpdump sidecar).
    """

    model_config = ConfigDict(frozen=True)

    dns_queries: list[DnsQuery] = Field(default_factory=list)
    http_requests: list[HttpRequest] = Field(default_factory=list)
    tcp_flows: list[NetworkFlow] = Field(default_factory=list)
    udp_flows: list[NetworkFlow] = Field(default_factory=list)


class RuntimeSignals(BaseModel):
    """Signaux collectés PENDANT l'exécution du sample.

    Complémentaire à SnapshotDiff (qui est avant/après).
    RuntimeSignals capture la dimension temporelle : ce qui s'est passé,
    dans quel ordre, avec quelle fréquence.

    syscalls_summary : agrégé depuis strace -f -tt -e trace=all (SYS_PTRACE).
    inotify_events : cappé à MAX_INOTIFY_EVENTS.
    sleep_cumulated_s : somme de tous les sleep/nanosleep — utilisé par
        hypothesis_evasion pour détecter les anti-sandbox sleeps.
    """

    model_config = ConfigDict(frozen=True)

    # Syscalls agrégés (strace -f → parsé ligne par ligne → agrégé)
    syscalls_summary: list[SyscallSummary] = Field(default_factory=list)

    # Événements filesystem temps-réel (inotifywait)
    inotify_events: Annotated[
        list[InotifyEvent],
        Field(max_length=MAX_INOTIFY_EVENTS),
    ] = Field(default_factory=list)

    # Réseau
    network: NetworkObservables = Field(default_factory=NetworkObservables)

    # Métadonnées d'exécution
    execution_duration_s: float
    sleep_cumulated_s: float = 0.0  # anti-sandbox sleep detection
    exit_code: int | None = None


# ---------------------------------------------------------------------------
# Couche 5 — MemoryObservables (/proc forensics post-exécution)
# ---------------------------------------------------------------------------


class PslistEntry(BaseModel):
    """Process vu dans /proc (pslist via procfs).

    Croisé avec SnapshotDiff.processes_spawned pour détecter les process
    cachés (présents dans /proc mais absents de ps auxf — rootkit classique).
    """

    model_config = ConfigDict(frozen=True)

    pid: int
    ppid: int
    comm: str


class MemoryRegion(BaseModel):
    """Région mémoire suspecte extraite depuis /proc/[pid]/maps.

    Critère principal : permissions RWX (readable + writable + executable).
    start_addr / end_addr en hexadécimal : "0x7f1234abcd".
    Pas de raw bytes — uniquement les métadonnées (sécurité + volumétrie).

    Protocole SIGSTOP :
        1. os.kill(pid, signal.SIGSTOP)  → geler le process
        2. parser /proc/{pid}/maps       → identifier régions RWX
        3. lire /proc/{pid}/mem          → dumper les régions suspectes
        4. extraire strings              → decoded_strings dans MemoryObservables
        5. os.kill(pid, signal.SIGKILL)  → terminer
    """

    model_config = ConfigDict(frozen=True)

    pid: int
    comm: str
    start_addr: str  # "0x7f..."
    end_addr: str  # "0x7f..."
    permissions: str  # "rwx", "rw-", "r-x", etc.
    size_bytes: int


class SyscallHook(BaseModel):
    """Entrée de la syscall table modifiée (détectée par comparaison /proc/kallsyms).

    is_kernel_symbol : True si le handler pointe vers un symbole kernel connu.
    False = hook suspect (rootkit, LKM malveillant).
    """

    model_config = ConfigDict(frozen=True)

    syscall_index: int
    handler_addr: str  # "0xffffffff..."
    symbol: str | None = None  # None si non résolu
    is_kernel_symbol: bool


class MemoryObservables(BaseModel):
    """Observables bruts extraits via /proc forensics (SIGSTOP).

    Remplace Volatility3 — aucun profil kernel requis.
    Tout ici est un FAIT observé — aucune classification.
    Les données partent dans features.memory_observables pour le LLM.

    hidden_pids : PIDs présents dans /proc mais absents de ps auxf
        → process caché (rootkit classique).

    decoded_strings : strings extraites des régions RWX via /proc/[pid]/mem.
        Cappées à MAX_DECODED_STRINGS × MAX_DECODED_STRING_CHARS (anti-injection).
        Peuvent contenir des URLs, IPs, commandes déchiffrées au runtime.
    """

    model_config = ConfigDict(frozen=True)

    # pslist via /proc
    pslist: list[PslistEntry] = Field(default_factory=list)
    hidden_pids: list[int] = Field(default_factory=list)  # croisement /proc vs ps

    # Régions RWX depuis /proc/[pid]/maps
    suspicious_regions: list[MemoryRegion] = Field(default_factory=list)

    # Hooks syscall table (comparaison /proc/kallsyms)
    syscall_hooks: list[SyscallHook] = Field(default_factory=list)

    # Strings déchiffrées dans les régions suspectes (via /proc/[pid]/mem + SIGSTOP)
    decoded_strings: Annotated[
        list[Annotated[str, Field(max_length=MAX_DECODED_STRING_CHARS)]],
        Field(max_length=MAX_DECODED_STRINGS),
    ] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Type alias — bundle complet passé aux hypothèses
# ---------------------------------------------------------------------------

# Les 6 modules d'hypothèse reçoivent ces 3 objets.
# Voir hypotheses/_types.py pour la signature evaluate().
AnalysisBundle = tuple[SnapshotDiff, RuntimeSignals, MemoryObservables]
