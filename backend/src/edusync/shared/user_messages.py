"""Every refusal shown to a school user is written in French, in the school's words (owner report 2026-11-06).

The domain keeps short, stable English messages for its own tests and logs (« Overlapping bands »). They must never
reach the screen: the API translates them here, in one place, for every module. A message that is not in the catalogue
and still looks English is replaced by a neutral French sentence (the original stays in the server logs).
tests/test_user_messages_french.py fails as soon as a new English message is raised without its French translation.
"""
from __future__ import annotations

import re

FRENCH: dict[str, str] = {
    # Annual exigibility policy (MEF) — settings
    "No fee rules": "Configurez au moins un frais avant d’activer la politique.",
    "Duplicate fee type": "Ce frais a déjà une règle dans cette politique.",
    "Custom prior-period policy requires percentage": "Indiquez le pourcentage dû pour les mois antérieurs à l’arrivée.",
    "Prior-period percentage requires CUSTOM mode": "Un pourcentage des mois antérieurs n’est possible qu’en mode « pourcentage ».",
    "Missing entry bands": "Ajoutez au moins une tranche de jours.",
    "Invalid band day": "Jour de tranche invalide : utilisez des jours de 1 à 31.",
    "Overlapping bands": "Les tranches de jours se chevauchent : chaque jour ne doit appartenir qu’à une seule tranche.",
    "Bands must cover every day of every month": "Les tranches doivent couvrir tout le mois, du 1er au dernier jour (la dernière tranche va « jusqu’à la fin du mois »).",
    "Invalid percentage": "Pourcentage invalide : entre 0 et 100.",
    "Draft policy not found": "Brouillon introuvable : il a peut-être déjà été activé.",
    "Academic year not found": "Année scolaire introuvable.",
    # Charges created at enrollment / regularisation
    "Positive due amount required for a new charge": "Le montant dû calculé pour ce frais est négatif : vérifiez le tarif et les avantages de l’élève.",
    "Payments cannot exist without a charge": "Un paiement existe sans frais correspondant : une régularisation financière est nécessaire.",
    "Existing charge amount is required": "Le montant du frais existant est introuvable : actualisez la fiche de l’élève puis réessayez.",
    "Invalid existing charge state": "Ce frais est déjà payé au-delà du nouveau montant : une correction financière explicite est nécessaire.",
    "Invalid paid amount": "Montant déjà payé invalide.",
    "Invalid tariff": "Tarif invalide : le montant doit être positif.",
    "Invalid month": "Mois invalide.",
    "Invalid monthly schedule period": "Période mensuelle invalide dans le barème : vérifiez les mois de l’année scolaire.",
    "Financial entry date required": "Indiquez la date d’entrée financière de l’élève.",
    "Negative recovery amount": "Le montant à recouvrer ne peut pas être négatif.",
    # Framework and authentication defaults (FastAPI / Starlette)
    "Not authenticated": "Votre session a expiré. Reconnectez-vous.",
    "no access token": "Votre session a expiré. Reconnectez-vous.",
    "Not Found": "La page ou la donnée demandée est introuvable.",
    "Method Not Allowed": "Cette action n’est pas disponible à cet endroit.",
    "Internal Server Error": "Une erreur technique est survenue de notre côté ; rien n’a été modifié. Réessayez dans un instant.",
    # Messaging providers (platform)
    "SENT requires a provider proof (message id)": "Envoi non confirmé par l’opérateur : aucun accusé de réception n’a été reçu.",
}

# Messages built with a variable part: (pattern, French template using the groups).
PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^unknown outcome (.+)$"), "Résultat d’envoi inconnu : {0}."),
)

GENERIC = "L’opération n’a pas pu aboutir. Vérifiez les informations saisies ; si le problème persiste, contactez l’administrateur."

_FRENCH_HINT = re.compile(
    r"[àâçéèêëîïôûùüÿœ’«»]|\b(le|la|les|de|du|des|un|une|est|sont|pour|par|sur|dans|avec|sans|au|aux|et|ou|ne|pas|plus|"
    r"cette|ce|cet|ces|votre|vos|déjà|aucun|aucune|introuvable|invalide|obligatoire|requis|requise|impossible|"
    r"indisponible|refusée?|inconnue?|manquantes?|trop|longue|insuffisant)\b", re.I)
_ENGLISH_HINT = re.compile(
    r"\b(the|is|are|was|must|required|requires|invalid|not|cannot|can't|without|found|missing|unknown|already|only|"
    r"negative|positive|duplicate|empty|exceeds?|too|for|of|with|no|should|failed|error|denied|forbidden)\b", re.I)


def looks_english(text: str) -> bool:
    return bool(_ENGLISH_HINT.search(text)) and not _FRENCH_HINT.search(text)


def to_french(text: str) -> str:
    """The French sentence for a refusal: catalogue first, then patterns; an unknown English message becomes GENERIC."""
    msg = (text or "").strip()
    if msg in FRENCH:
        return FRENCH[msg]
    for pattern, template in PATTERNS:
        m = pattern.match(msg)
        if m:
            return template.format(*m.groups())
    if msg and looks_english(msg):
        return GENERIC
    return text
