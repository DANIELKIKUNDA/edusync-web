"""CI secret scan (no third-party tool): fails if a tracked file contains a high-confidence secret pattern.

Complements the certification scan (which compares the real local secrets): in CI there is no secret to compare, so
only unambiguous formats are searched — private keys, service-account keys, cloud / Git provider tokens. A match is
reported by file and line, never with the matched value.
    python tools/ci/secret_patterns.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATTERNS = {
    "private key (PEM)": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "service account private key": re.compile(r'"private_key"\s*:\s*"-----BEGIN'),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{60,}\b"),
    "Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    "Stripe live key": re.compile(r"\b(?:sk|rk)_live_[0-9A-Za-z]{20,}\b"),
}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".ico", ".pdf", ".xlsx", ".zip", ".woff2", ".lock"}
# This scanner itself contains the patterns.
SKIP_FILES = {"tools/ci/secret_patterns.py"}


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f and f not in SKIP_FILES and Path(f).suffix.lower() not in SKIP_SUFFIXES]


def main() -> int:
    hits = []
    files = tracked_files()
    for rel in files:
        p = ROOT / rel
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for label, rx in PATTERNS.items():
                m = rx.search(line)
                # Values published by provider documentation as examples (e.g. AWS ...EXAMPLE) are test vectors, not secrets.
                if m and "EXAMPLE" not in m.group(0):
                    hits.append(f"{rel}:{n}: {label}")
    for h in hits:
        print("SECRET", h)
    print(f"== {len(files)} fichiers suivis analysés : {len(hits)} secret(s) détecté(s)")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
