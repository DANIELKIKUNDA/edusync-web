"""Writes the owner's private test-account sheet: .local/RECETTE_COMPTES.md (never versioned).

    python tools/local/recette_accounts.py

Reads the private fixtures created by the certification probes (.local/claude-fixtures-*.json) and the
live demo database to list schools, school codes, accounts and their current roles. Passwords appear only
in this private file on the owner's workstation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from edusync_local import PORTS, load_env  # noqa: E402

LABELS = {"ADMIN": "Administrateur système de l’école", "CAISSIER1": "Caissier 1", "CAISSIER2": "Caissier 2", "GEST": "Gestionnaire",
          "SECR": "Secrétariat", "R_PROMOTEUR": "Promoteur", "R_RESPONSABLE_FINANCE": "Responsable Finance", "INTENDANT": "Intendant",
          "CLOSURE_RF": "Responsable Finance (recette clôture)", "CLOSURE_DOCS": "Secrétariat (recette clôture)"}


def main() -> None:
    env = load_env("demo")
    from sqlalchemy import create_engine, text
    eng = create_engine(env["EDUSYNC_OWNER_DATABASE_URL"])
    fx = json.loads((ROOT / ".local" / "claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
    out = ["# EduSync — comptes de recette locale (PRIVÉ, ne pas diffuser)", "",
           f"Adresse : http://localhost:{PORTS['app']}/  (raccourci bureau « EduSync »)", "",
           "## Manager Système (Atelier Pro)", "",
           f"- Connexion : bouton « Accès Atelier Pro (Manager système) » sur la page de connexion",
           f"- E-mail : {env['EDUSYNC_PLATFORM_ADMIN_EMAIL']}", f"- Mot de passe : {env['EDUSYNC_PLATFORM_ADMIN_PASSWORD']}", ""]
    # Second factor (option B): the probes enrolled this local test account; its key lets the owner add it to a phone.
    mfa = fx.get("MFA_TOTP", {}).get(env["EDUSYNC_PLATFORM_ADMIN_EMAIL"].strip().lower())
    if mfa:
        from urllib.parse import quote
        uri = (f"otpauth://totp/{quote('EduSync:' + env['EDUSYNC_PLATFORM_ADMIN_EMAIL'], safe='@:')}"
               f"?secret={mfa['secret']}&issuer=EduSync%20Atelier%20Pro&algorithm=SHA1&digits=6&period=30")
        out += ["- Validation en deux étapes : obligatoire. Ajoutez ce compte de recette à votre application d’authentification",
                f"  (Google/Microsoft Authenticator → « Saisir une clé ») : clé **`{mfa['secret']}`**, type « basé sur l’heure ».",
                f"  Lien direct (téléphone) : `{uri}`",
                f"- Codes de secours de recette encore connus : {', '.join(f'`{c}`' for c in mfa.get('recovery_codes', [])[:3])}…", ""]
    with eng.connect() as c:
        for key in ("A", "B", "C"):
            school = fx.get(key)
            if not school:
                continue
            row = c.execute(text("SELECT name,code,status FROM schools WHERE id=:i"), {"i": school["school_id"]}).first()
            if not row:
                continue
            out += [f"## {row.name}", "", f"- Code établissement : **{row.code}**  ·  statut : {row.status}", "",
                    "| Profil | E-mail | Mot de passe | Rôles actuels | Accès |", "|---|---|---|---|---|"]
            for ukey, u in school.get("users", {}).items():
                if ukey not in LABELS:
                    continue
                roles = c.execute(text("""SELECT string_agg(DISTINCT r.label, ', ') FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
                    WHERE a.membership_id=:m AND a.active AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now())"""), {"m": u.get("membership_id")}).scalar()
                active = c.execute(text("SELECT m.active AND us.active FROM school_memberships m JOIN users us ON us.id=m.user_id WHERE m.id=:m"), {"m": u.get("membership_id")}).scalar()
                out.append(f"| {LABELS[ukey]} | {u['email']} | `{u['password']}` | {roles or '—'} | {'actif' if active else 'désactivé'} |")
            out.append("")
    blank = ROOT / ".local" / "closure" / "blank-manager.txt"
    out += ["## Environnement vierge (installation neuve)", "",
            "Démarrage : `tools\\local\\EduSync-Demarrer.cmd --profile blank` (ou `python tools/local/edusync_local.py start --profile blank`).",
            "Sur une base vierge, la page de connexion propose « Créer le Manager Système » une seule fois.", ""]
    if blank.exists():
        email, pw = blank.read_text(encoding="utf-8").split()[:2]
        out += [f"Manager créé pendant la recette sur la base vierge actuelle : {email} / `{pw}`", ""]
    target = ROOT / ".local" / "RECETTE_COMPTES.md"
    target.write_text("\n".join(out), encoding="utf-8")
    print(f"Fiche privée écrite : {target}")


if __name__ == "__main__":
    main()
