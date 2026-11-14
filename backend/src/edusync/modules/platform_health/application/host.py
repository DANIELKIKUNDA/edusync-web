"""Ressources du serveur (owner, 2026-11-14 — supervision avant la première école, VPS de 4 Go).

Measured from inside the API container, at no cost: without a memory limit nor lxcfs, /proc/meminfo and /proc/loadavg
of a Docker container are those of the HOST, and statvfs("/") reads the host filesystem that holds the Docker volumes.
No agent, no extra container. Coolify keeps the CPU / memory history (Sentinel) and alerts on disk usage; this
component adds what Coolify does not alert on — memory and CPU saturation — and feeds the same incident e-mails and
the external heartbeat (heartbeat.py) as every other component.

States: OK, DEGRADED (warning, shown on the screen) and DOWN (critical: an incident after the alert delay). A machine
where /proc is not readable (developer laptop) reports NOT_CONFIGURED, never a made-up figure.
"""
from __future__ import annotations

import os
from typing import Any

LABEL = "Ressources du serveur"


def _meminfo(path: str) -> tuple[int, int]:
    values: dict[str, int] = {}
    with open(path, encoding="ascii") as f:
        for line in f:
            name, _, rest = line.partition(":")
            if name in ("MemTotal", "MemAvailable"):
                values[name] = int(rest.split()[0])
    return values["MemTotal"], values["MemAvailable"]


def _load5(path: str) -> float:
    with open(path, encoding="ascii") as f:
        return float(f.read().split()[1])


def _pct(v: float) -> str:
    return f"{v:.0f} %"


def host_component(settings: Any, *, proc: str = "/proc", disk_path: str | None = None, cpus: int | None = None) -> dict:
    try:
        total, available = _meminfo(f"{proc}/meminfo")
        load = _load5(f"{proc}/loadavg")
        st = os.statvfs(disk_path or settings.host_disk_path)
    except (OSError, KeyError, ValueError, IndexError, AttributeError):
        return {"key": "host", "label": LABEL, "state": "NOT_CONFIGURED", "detail": "Mesure indisponible sur cette machine", "measured_ms": None}
    cpus = max(1, cpus or os.cpu_count() or 1)
    mem = 100.0 * (total - available) / total if total else 0.0
    disk_total = st.f_blocks * st.f_frsize
    disk = 100.0 * (disk_total - st.f_bavail * st.f_frsize) / disk_total if disk_total else 0.0
    per_cpu = load / cpus

    problems: list[tuple[str, str]] = []          # (state, explanation)
    for value, warn, crit, text in (
        (mem, settings.host_memory_warn_percent, settings.host_memory_critical_percent, f"mémoire utilisée à {_pct(mem)}"),
        (disk, settings.host_disk_warn_percent, settings.host_disk_critical_percent, f"disque rempli à {_pct(disk)}"),
        (per_cpu, settings.host_load_warn_per_cpu, settings.host_load_critical_per_cpu,
         f"processeur saturé (charge {load:.1f} pour {cpus} cœur{'s' if cpus > 1 else ''})"),
    ):
        if value >= crit:
            problems.append(("DOWN", text))
        elif value >= warn:
            problems.append(("DEGRADED", text))
    state = "DOWN" if any(s == "DOWN" for s, _ in problems) else "DEGRADED" if problems else "OK"
    summary = f"Mémoire {_pct(mem)} · Disque {_pct(disk)} · Charge {load:.1f} ({cpus} cœur{'s' if cpus > 1 else ''})"
    detail = summary if not problems else "Attention : " + ", ".join(t for _, t in problems) + f" — {summary}"
    return {"key": "host", "label": LABEL, "state": state, "detail": detail, "measured_ms": None,
            "host": {"memory_percent": round(mem, 1), "memory_total_mb": total // 1024, "memory_available_mb": available // 1024,
                     "disk_percent": round(disk, 1), "disk_free_gb": round(st.f_bavail * st.f_frsize / 1024 ** 3, 1),
                     "load_5min": load, "cpus": cpus}}
