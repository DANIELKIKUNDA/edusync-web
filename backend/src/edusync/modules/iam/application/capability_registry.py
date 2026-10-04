from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from edusync.modules.iam.domain.authorization import Capability, RiskLevel


@dataclass(frozen=True, slots=True)
class CapabilityRegistry:
    capabilities: tuple[Capability, ...]

    @classmethod
    def from_json(cls, path: str | Path) -> "CapabilityRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        capabilities = tuple(
            Capability(
                code=item["code"],
                domain=item["domain"],
                group=item["group"],
                label=item["label"],
                action=item["action"],
                risk=RiskLevel(item["risk"]),
                offline_policy=item["offline_policy"],
                audit_required=bool(item["audit_required"]),
                scope_types=tuple(item.get("scope_types", [])),
                outputs=tuple(item.get("outputs", [])),
                sensitive=bool(item.get("sensitive", False)),
                source_status=item.get("source_status", ""),
                prerequisites=tuple(item.get("prerequisites", [])),
                notes=item.get("notes", ""),
            )
            for item in payload["capabilities"]
        )
        registry = cls(capabilities)
        registry.validate(expected_count=int(payload["capability_count"]))
        return registry

    def validate(self, expected_count: int | None = None) -> None:
        codes = [c.code for c in self.capabilities]
        if len(codes) != len(set(codes)):
            raise ValueError("Codes de capacités dupliqués")
        if expected_count is not None and len(codes) != expected_count:
            raise ValueError(f"Registre incomplet: {len(codes)} != {expected_count}")
        for c in self.capabilities:
            if c.risk in {RiskLevel.HIGH, RiskLevel.CRITICAL} and c.action not in {"read", "filter", "export", "print", "drilldown"}:
                # High-risk mutations are expected to be audited unless an explicit
                # documented exception is added later.
                if not c.audit_required:
                    raise ValueError(f"Mutation à risque non auditée: {c.code}")

    def by_code(self) -> dict[str, Capability]:
        return {c.code: c for c in self.capabilities}

    def tree(self) -> dict[str, dict[str, tuple[Capability, ...]]]:
        result: dict[str, dict[str, list[Capability]]] = {}
        for capability in self.capabilities:
            result.setdefault(capability.domain, {}).setdefault(capability.group, []).append(capability)
        return {
            domain: {group: tuple(sorted(items, key=lambda c: c.code)) for group, items in groups.items()}
            for domain, groups in result.items()
        }

    def subset(self, codes: Iterable[str]) -> tuple[Capability, ...]:
        by_code = self.by_code()
        missing = [code for code in codes if code not in by_code]
        if missing:
            raise KeyError(f"Capacités inconnues: {', '.join(missing)}")
        return tuple(by_code[code] for code in codes)
