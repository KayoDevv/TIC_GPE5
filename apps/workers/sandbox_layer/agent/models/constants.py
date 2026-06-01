"""Security / volumetry constants + watched paths (sandbox contract).

Centralises the anti-volumetry / anti-prompt-injection caps and the watched
filesystem path lists, shared by the `models/` submodules.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Security / volumetry caps
# ---------------------------------------------------------------------------

MAX_INOTIFY_EVENTS: int = 10_000
MAX_CMDLINE_CHARS: int = 512
MAX_DECODED_STRING_CHARS: int = 128
MAX_DECODED_STRINGS: int = 500
MAX_SYSCALL_SAMPLE_ARGS: int = 20
MAX_SYSCALL_ARG_CHARS: int = 256

# Watched filesystem paths (excluding /usr /lib /bin → too static)
WATCHED_PATHS: tuple[str, ...] = (
    "/etc",
    "/home",
    "/tmp",
    "/var",
    "/opt",
    "/root",
)

# Known persistence paths
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
