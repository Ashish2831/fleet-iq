"""Validation strictness strategy — strict vs lenient for forms vs imports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ValidationStrategy(ABC):
    @abstractmethod
    def apply(self, errors: list[str]) -> ValidationResult: ...


class StrictValidationStrategy(ValidationStrategy):
    def apply(self, errors: list[str]) -> ValidationResult:
        return ValidationResult(ok=not errors, errors=list(errors))


class LenientValidationStrategy(ValidationStrategy):
    def apply(self, errors: list[str]) -> ValidationResult:
        if not errors:
            return ValidationResult(ok=True)
        return ValidationResult(ok=True, warnings=list(errors))


def validate_required(data: dict, keys: list[str], strategy: ValidationStrategy | None = None) -> ValidationResult:
    strategy = strategy or StrictValidationStrategy()
    missing = [k for k in keys if data.get(k) in (None, "")]
    return strategy.apply([f"{k} is required" for k in missing])
