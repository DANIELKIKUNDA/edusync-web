"""Owner, 2026-11-19: the report leaves by e-mail « avec le PDF joint », to each responsible in his own scope."""
from edusync.shared.messaging.email_smtp import SmtpEmailProvider
from edusync.shared.messaging.ports import EmailContent
from edusync.modules.finance_recovery.application.digest_send import letter_text


def test_smtp_message_carries_the_pdf():
    p = SmtpEmailProvider.__new__(SmtpEmailProvider)
    p.from_name, p.from_email = "EduSync", "noreply@example.test"
    msg = p.build(to="promoteur@example.test", content=EmailContent("Votre semaine", "Bonjour", None, {}, [("rapport.pdf", "application/pdf", b"%PDF-1.4 x")]))
    parts = [x for x in msg.iter_attachments()]
    assert len(parts) == 1 and parts[0].get_filename() == "rapport.pdf" and parts[0].get_content_type() == "application/pdf"
    assert parts[0].get_content() == b"%PDF-1.4 x"


def test_letter_text_reads_like_the_pdf():
    t = letter_text("Bonjour Monsieur le Promoteur,", [("", "Voici la semaine."), ("L’argent", "L’école a encaissé 10 FC.")], "EduSync — pour APN")
    assert t.startswith("Bonjour Monsieur le Promoteur,\n\nVoici la semaine.\n\nL’argent : L’école a encaissé 10 FC.")
    assert "pièce jointe" in t and t.endswith("EduSync — pour APN")
