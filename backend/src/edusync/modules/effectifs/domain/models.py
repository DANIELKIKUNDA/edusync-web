from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Iterable, Mapping, Any


class HeadcountScope(StrEnum):
    ALL = "ALL"
    MATERNELLE = "MATERNELLE"
    PRIMAIRE = "PRIMAIRE"
    SECONDAIRE = "SECONDAIRE"


class HeadcountGroup(StrEnum):
    CLASS = "class"
    SECTION = "section"
    OPTION = "option"


@dataclass(frozen=True, slots=True)
class FGT:
    female: int = 0
    male: int = 0
    total: int = 0

    @classmethod
    def from_genders(cls, genders: Iterable[str | None]) -> "FGT":
        values=list(genders)
        f=sum(1 for x in values if x == "F")
        m=sum(1 for x in values if x == "M")
        return cls(female=f, male=m, total=len(values))


@dataclass(frozen=True, slots=True)
class HeadcountRow:
    section: str
    label: str
    code: str
    enrolled: FGT
    abandoned: FGT
    transferred: FGT
    active: FGT


def _fgt_add(a: FGT, b: FGT) -> FGT:
    return FGT(a.female+b.female, a.male+b.male, a.total+b.total)


def total_headcount(rows: Iterable[HeadcountRow]) -> HeadcountRow:
    enrolled=abandoned=transferred=active=FGT()
    for row in rows:
        enrolled=_fgt_add(enrolled,row.enrolled)
        abandoned=_fgt_add(abandoned,row.abandoned)
        transferred=_fgt_add(transferred,row.transferred)
        active=_fgt_add(active,row.active)
    return HeadcountRow(section="",label="Total général",code="TOTAL",enrolled=enrolled,abandoned=abandoned,transferred=transferred,active=active)


def row_from_mapping(row: Mapping[str, Any]) -> HeadcountRow:
    def f(prefix: str) -> FGT:
        return FGT(int(row.get(f"{prefix}_f") or 0),int(row.get(f"{prefix}_m") or 0),int(row.get(f"{prefix}_t") or 0))
    return HeadcountRow(
        section=str(row.get("section_label") or row.get("section") or "—"),
        label=str(row.get("label") or "—"),
        code=str(row.get("code") or ""),
        enrolled=f("enrolled"), abandoned=f("abandoned"), transferred=f("transferred"), active=f("active")
    )


@dataclass(frozen=True, slots=True)
class MaterialDeposit:
    quantity: Decimal
    unit: str

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("La quantité déposée doit être strictement positive")
        if not self.unit.strip():
            raise ValueError("L'unité de contribution est obligatoire")
