#!/usr/bin/env python3
"""Publish a truthful *external* EduSync CI commit status to GitHub.

This is NOT GitHub Actions, a GitHub Check Run, or a production deploy gate.
Must run only on a trusted, isolated CI host after the actual tests.
"""
from __future__ import annotations

import json
import os
import re
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = "DANIELKIKUNDA/edusync-web"
CONTEXT = "external/edusync-ci"
STATES = {"pending", "success", "failure", "error"}
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
MAX_TOKEN_BYTES = 4096


def read_token(path_text: str) -> str:
    if not path_text:
        raise ValueError("EDUSYNC_GITHUB_STATUS_TOKEN_FILE non configure")
    path = Path(path_text)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("La cle doit etre un fichier regulier")
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise ValueError("La cle doit appartenir au compte CI et etre chmod 600")
        raw = os.read(fd, MAX_TOKEN_BYTES + 1)
        if len(raw) > MAX_TOKEN_BYTES:
            raise ValueError("Fichier jeton trop long")
        token = raw.decode("ascii").strip()
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", token) or len(token) < 16:
            raise ValueError("Format du jeton GitHub inattendu")
        return token
    finally:
        os.close(fd)


def main() -> int:
    if len(sys.argv) < 4:
        print("Usage: fallback_github_status.py SHA pending|success|failure|error DESCRIPTION", file=sys.stderr)
        return 64
    sha, state = sys.argv[1:3]
    description = " ".join(sys.argv[3:]).strip()
    if not SHA_PATTERN.fullmatch(sha) or state not in STATES or not description or len(description) > 130:
        print("SHA, statut ou description invalide", file=sys.stderr)
        return 64

    try:
        token = read_token(os.environ.get("EDUSYNC_GITHUB_STATUS_TOKEN_FILE", ""))
        payload = json.dumps({
            "state": state, "context": CONTEXT, "description": description
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.github.com/repos/{REPO}/statuses/{sha}",
            data=payload, method="POST",
            headers={
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "EduSync-External-CI",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as res:
            if res.status != 201:
                raise RuntimeError(f"GitHub status HTTP {res.status}")
        print(f"Statut GitHub externe publie : {sha[:12]} {CONTEXT}={state}")
        return 0
    except (OSError, ValueError, UnicodeError, urllib.error.URLError, RuntimeError) as exc:
        # Never display the token, request or headers on failure.
        kind = type(exc).__name__
        print(f"Publication statut externe impossible ({kind}); consulter configuration/reseau/permissions", file=sys.stderr)
        return 74


if __name__ == "__main__":
    raise SystemExit(main())
