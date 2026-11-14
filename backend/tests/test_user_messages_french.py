"""Owner report 2026-11-06: « Positive due amount required for a new charge » reached the enrollment screen in English.
Every refusal must reach the school in French: this guard scans every message the server code raises."""
import pathlib
import re

from edusync.shared.user_messages import FRENCH, GENERIC, PATTERNS, looks_english, to_french

ROOT = pathlib.Path(__file__).resolve().parents[1] / "src" / "edusync"
RAISE = re.compile(r"""(?:raise\s+[A-Za-z_.]*(?:Error|Exception|Denied|Conflict)\(|detail\s*=\s*)f?(["'])(.+?)\1""")


def _raised_messages():
    for path in ROOT.rglob("*.py"):
        for m in RAISE.finditer(path.read_text(encoding="utf-8")):
            yield path.relative_to(ROOT), m.group(2)


def test_every_english_message_raised_by_the_server_has_a_french_translation():
    missing = sorted({f"{p}: {msg}" for p, msg in _raised_messages()
                      if looks_english(msg) and msg not in FRENCH and not any(rx.match(msg) for rx, _ in PATTERNS)})
    assert not missing, "Ajoutez la traduction dans edusync/shared/user_messages.py :\n" + "\n".join(missing)


def test_the_enrollment_refusal_is_translated():
    assert "négatif" in to_french("Positive due amount required for a new charge")
    assert to_french("Overlapping bands").startswith("Les tranches de jours se chevauchent")
    assert to_french("unknown outcome X") == "Résultat d’envoi inconnu : X."


def test_french_sentences_are_kept_and_unknown_english_becomes_a_neutral_french_sentence():
    assert to_french("Classe introuvable") == "Classe introuvable"
    assert to_french("Stock insuffisant : 3 disponible(s)") == "Stock insuffisant : 3 disponible(s)"
    assert to_french("Something is not valid for this request") == GENERIC
    assert all(not looks_english(v) for v in FRENCH.values())


def test_the_api_translates_every_http_refusal_in_one_place():
    app = (ROOT / "bootstrap" / "app.py").read_text(encoding="utf-8")
    assert "@app.exception_handler(_StarletteHTTPException)" in app and "to_french(detail)" in app
