"""Transactional e-mail templates (plain text + HTML). Standard library only: every interpolated value is HTML-escaped,
so a name typed by a user can never inject markup. No password and no personal data beyond the recipient's name is
ever written in an e-mail; links are single-use and expire (see account tokens)."""
from __future__ import annotations

from html import escape

from edusync.shared.messaging.ports import EmailContent

_WRAP = """<!doctype html><html lang="fr"><body style="margin:0;background:#f4f6fb;font-family:Arial,Helvetica,sans-serif;color:#0b2a5c">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="100%" style="max-width:560px;background:#ffffff;border-radius:12px;padding:28px" cellpadding="0" cellspacing="0">
<tr><td style="font-size:20px;font-weight:bold;padding-bottom:12px">EduSync</td></tr>
<tr><td style="font-size:15px;line-height:1.6">{body}</td></tr>
<tr><td style="font-size:12px;color:#5b6b82;padding-top:24px">Message automatique d’EduSync : ne répondez pas à cet e-mail.</td></tr>
</table></td></tr></table></body></html>"""


def _button(url: str, label: str) -> str:
    return (f'<p style="margin:24px 0"><a href="{escape(url, quote=True)}" style="background:#0b2a5c;color:#ffffff;'
            f'padding:12px 20px;border-radius:8px;text-decoration:none;display:inline-block">{escape(label)}</a></p>')


def render(template_code: str | None, *, recipient_name: str | None, school_name: str | None, subject: str | None,
           body: str, link: str | None, ttl_label: str | None = None) -> EmailContent:
    name = (recipient_name or "").strip() or "Bonjour"
    hello = f"Bonjour {name}," if recipient_name else "Bonjour,"
    if template_code == "ACCOUNT_INVITATION":
        where = f" de {school_name}" if school_name else ""
        text = (f"{hello}\n\nVous êtes invité(e) à rejoindre l’espace EduSync{where}.\n"
                f"Pour activer votre compte et choisir votre mot de passe, ouvrez ce lien (valable {ttl_label}, utilisable une seule fois) :\n"
                f"{link}\n\nSi vous n’attendiez pas cette invitation, ignorez ce message.")
        html = _WRAP.format(body=f"<p>{escape(hello)}</p><p>Vous êtes invité(e) à rejoindre l’espace EduSync{escape(where)}.</p>"
                                 f"{_button(link or '', 'Activer mon compte')}<p>Ce lien est valable {escape(ttl_label or '')} et ne peut servir qu’une fois. "
                                 "Aucun mot de passe ne vous est envoyé.</p><p>Si vous n’attendiez pas cette invitation, ignorez ce message.</p>")
        return EmailContent("Invitation à rejoindre EduSync", text, html)
    if template_code == "ACCOUNT_PASSWORD_RESET":
        text = (f"{hello}\n\nUne réinitialisation du mot de passe de votre compte EduSync a été demandée.\n"
                f"Ouvrez ce lien pour choisir un nouveau mot de passe (valable {ttl_label}, utilisable une seule fois) :\n{link}\n\n"
                "Si vous n’êtes pas à l’origine de cette demande, ignorez ce message : votre mot de passe actuel reste valable.")
        html = _WRAP.format(body=f"<p>{escape(hello)}</p><p>Une réinitialisation du mot de passe de votre compte EduSync a été demandée.</p>"
                                 f"{_button(link or '', 'Choisir un nouveau mot de passe')}<p>Ce lien est valable {escape(ttl_label or '')} et ne peut servir qu’une fois.</p>"
                                 "<p>Si vous n’êtes pas à l’origine de cette demande, ignorez ce message : votre mot de passe actuel reste valable.</p>")
        return EmailContent("Réinitialisation de votre mot de passe EduSync", text, html)
    if template_code == "ACCOUNT_SECURITY_ALERT":
        text = (f"{hello}\n\n{body}\n\nSi vous n’êtes pas à l’origine de cette action, contactez immédiatement l’administrateur "
                "de votre école ou le support EduSync.")
        html = _WRAP.format(body=f"<p>{escape(hello)}</p><p>{escape(body)}</p><p>Si vous n’êtes pas à l’origine de cette action, "
                                 "contactez immédiatement l’administrateur de votre école ou le support EduSync.</p>")
        return EmailContent(subject or "Alerte de sécurité EduSync", text, html)
    # School communication (communiqué): the text written by the school, escaped.
    title = subject or (f"Message de {school_name}" if school_name else "Message de votre école")
    text = f"{hello}\n\n{body}\n\n— {school_name or 'Votre école'} (via EduSync)"
    paragraphs = "".join(f"<p>{escape(p)}</p>" for p in body.split("\n") if p.strip())
    html = _WRAP.format(body=f"<p>{escape(hello)}</p>{paragraphs}<p>— {escape(school_name or 'Votre école')}</p>")
    return EmailContent(title[:180], text, html)
