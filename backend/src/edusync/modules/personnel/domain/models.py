from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4


class StaffStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    INACTIVE = "INACTIVE"
    LEFT = "LEFT"


class StaffCategory(StrEnum):
    ENSEIGNANT = "ENSEIGNANT"
    ADMINISTRATIF = "ADMINISTRATIF"
    OUVRIER = "OUVRIER"
    AUTRE = "AUTRE"


class AssignmentScope(StrEnum):
    SCHOOL = "SCHOOL"
    SECTION = "SECTION"
    CLASS = "CLASS"


@dataclass(slots=True)
class StaffMember:
    school_id: UUID
    employee_no: str
    last_name: str
    first_name: str | None = None
    middle_name: str | None = None
    category: StaffCategory = StaffCategory.AUTRE
    id: UUID = field(default_factory=uuid4)
    gender: str | None = None
    birth_date: date | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    qualification: str | None = None
    specialty: str | None = None
    hire_date: date | None = None
    status: StaffStatus = StaffStatus.ACTIVE
    exit_date: date | None = None
    exit_reason: str | None = None
    photo_url: str | None = None
    notes: str | None = None
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self.employee_no = self.employee_no.strip().upper()
        self.last_name = self.last_name.strip()
        self.first_name = self.first_name.strip() if self.first_name else None
        self.middle_name = self.middle_name.strip() if self.middle_name else None
        if not self.employee_no or not self.last_name:
            raise ValueError("Matricule agent et nom obligatoires")
        if self.gender not in {None, "M", "F", "X"}:
            raise ValueError("Sexe invalide")
        if self.status == StaffStatus.LEFT and self.exit_date is None:
            raise ValueError("Une sortie exige une date effective")
        if self.hire_date and self.exit_date and self.exit_date < self.hire_date:
            raise ValueError("La sortie ne peut pas précéder l'engagement")

    @property
    def display_name(self) -> str:
        return " ".join(x for x in (self.last_name, self.middle_name, self.first_name) if x)

    def leave(self, *, effective_date: date, reason: str) -> None:
        reason = reason.strip()
        if self.status == StaffStatus.LEFT:
            raise ValueError("Cet agent est déjà sorti")
        if not reason:
            raise ValueError("Le motif de sortie est obligatoire")
        if self.hire_date and effective_date < self.hire_date:
            raise ValueError("La date de sortie ne peut pas précéder l'engagement")
        self.status = StaffStatus.LEFT
        self.exit_date = effective_date
        self.exit_reason = reason

    def reactivate(self) -> None:
        if self.status != StaffStatus.LEFT:
            raise ValueError("Seul un ancien agent peut être réactivé")
        self.status = StaffStatus.ACTIVE
        self.exit_date = None
        self.exit_reason = None


@dataclass(slots=True)
class StaffFunction:
    school_id: UUID
    code: str
    label: str
    category: str = "AUTRE"
    id: UUID = field(default_factory=uuid4)
    enabled: bool = True
    sort_order: int = 100
    version: int = 1

    def __post_init__(self) -> None:
        self.code = self.code.strip().upper().replace(" ", "_")
        self.label = self.label.strip()
        if not self.code or not self.label:
            raise ValueError("Code et libellé de fonction obligatoires")


@dataclass(slots=True)
class StaffAssignment:
    school_id: UUID
    staff_id: UUID
    function_id: UUID
    start_date: date
    scope_type: AssignmentScope = AssignmentScope.SCHOOL
    scope_value: str | None = None
    section_id: UUID | None = None
    class_id: UUID | None = None
    is_primary: bool = False
    is_titular: bool = False
    titular_class_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    end_date: date | None = None
    end_reason: str | None = None
    version: int = 1

    def __post_init__(self) -> None:
        if self.scope_type == AssignmentScope.SCHOOL:
            if self.scope_value or self.section_id or self.class_id:
                raise ValueError("Le périmètre école ne porte aucune section/classe")
        elif self.scope_type == AssignmentScope.SECTION:
            if not self.scope_value or not self.section_id or self.class_id:
                raise ValueError("Le périmètre section exige la section")
        elif self.scope_type == AssignmentScope.CLASS:
            if not self.scope_value or not self.class_id:
                raise ValueError("Le périmètre classe exige la classe")
        if self.is_titular != (self.titular_class_id is not None):
            raise ValueError("Le titulariat et sa classe doivent être renseignés ensemble")
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("La fin d'affectation ne peut pas précéder le début")

    def end(self, *, effective_date: date, reason: str) -> None:
        reason = reason.strip()
        if self.end_date is not None:
            raise ValueError("Cette affectation est déjà clôturée")
        if effective_date < self.start_date:
            raise ValueError("La fin d'affectation ne peut pas précéder son début")
        if not reason:
            raise ValueError("Le motif de fin d'affectation est obligatoire")
        self.end_date = effective_date
        self.end_reason = reason


@dataclass(frozen=True, slots=True)
class StaffSummary:
    total: int
    active: int
    suspended: int
    left: int
    teachers: int
    administrative: int
    workers: int
    other: int
    active_assignments: int
    linked_accounts: int
    staff_children: int
