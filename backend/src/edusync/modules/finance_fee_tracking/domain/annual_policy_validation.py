"""Validate annual fee rules before persistence or activation."""
from decimal import Decimal
from edusync.modules.finance_fee_tracking.domain.annual_exigibility import DayBand, EntryPolicy, PriorPeriodMode

def validate_policy_rules(rules):
    if not rules:
        raise ValueError("No fee rules")
    seen = set()
    for rule in rules:
        fee_id = str(rule["fee_type_id"])
        if fee_id in seen:
            raise ValueError("Duplicate fee type")
        seen.add(fee_id)
        bands = tuple(
            DayBand(int(b["first_day"]),
                    int(b["last_day"]) if b.get("last_day") is not None else None,
                    Decimal(str(b["percent"])))
            for b in rule["bands"]
        )
        EntryPolicy(
            PriorPeriodMode(rule["prior_mode"]), bands,
            Decimal(str(rule["prior_percent"])) if rule.get("prior_percent") is not None else None,
        )
    return len(seen)


# Messages shown to a school administrator (the domain keeps stable English messages for its tests and logs).
_FRENCH = {
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
}


def french_policy_error(exc: Exception) -> ValueError:
    """The same error, worded for the school administrator."""
    return ValueError(_FRENCH.get(str(exc), str(exc)))
