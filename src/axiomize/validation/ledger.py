"""Kanita dayali confidence ledger (GAP-3).

Saf modul: disaridan verilen symbolic / numerical / cross-validation /
falsification / uncertainty girdilerini alip her birini ayri ayri
isaretler ve agirlikli bir guven skoru uretir.

Kurallar:
- Hicbir girdi uydurulmaz: degeri verilmeyen kanit ``UNVERIFIED`` sayilir.
- Girdi olarak ``ValidationStatus``, durum adi (``"PASS"`` vb.) veya
  ``{"status": ..., "detail": ...}`` seklinde sozluk kabul edilir.
- ``TOOL_UNAVAILABLE`` ve ``UNVERIFIED`` girdiler skor paydasina katilmaz
  (agirliklari dagitilir); skor yalnizca hukmu verilmis girdilerden uretilir.
- Ham ``UncertaintyReport`` (``to_dict()`` olan nesne) tek basina hukmuz
  vermez: ici bossa da dolu da olsa ``UNVERIFIED`` isaretlenir; hukkum
  icin cagiranin acik ``status`` vermesi gerekir.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from axiomize.validation.status import ValidationStatus

EVIDENCE_KINDS: tuple[str, ...] = (
    "symbolic",
    "numerical",
    "cross_validation",
    "falsification",
    "uncertainty",
)

DEFAULT_WEIGHTS: dict[str, float] = {
    "symbolic": 0.25,
    "numerical": 0.25,
    "cross_validation": 0.20,
    "falsification": 0.20,
    "uncertainty": 0.10,
}

# Hukmu verilmis durumlarin sayisal karsiligi. None = skora katilmaz.
_SCORES: dict[ValidationStatus, float | None] = {
    ValidationStatus.PASS: 1.0,
    ValidationStatus.WARNING: 0.6,
    ValidationStatus.INCONCLUSIVE: 0.5,
    ValidationStatus.CONFLICT: 0.3,
    ValidationStatus.FAIL: 0.0,
    ValidationStatus.TOOL_UNAVAILABLE: None,
    ValidationStatus.UNVERIFIED: None,
}

_ALIASES = {
    "CROSSVALIDATION": "cross_validation",
    "CROSS-VALIDATION": "cross_validation",
    "CROSS_VALIDATION": "cross_validation",
    "XVAL": "cross_validation",
}


def _normalize_kind(kind: str) -> str:
    key = kind.strip().lower().replace("-", "_").replace(" ", "_")
    key = _ALIASES.get(kind.strip().upper(), key)
    if key not in EVIDENCE_KINDS:
        raise ValueError(f"bilinmeyen kanit turu: {kind!r}")
    return key


def _coerce_status(value: Any) -> ValidationStatus | None:
    if value is None or isinstance(value, ValidationStatus):
        return value
    if isinstance(value, str):
        try:
            return ValidationStatus[value.strip().upper()]
        except KeyError:
            raise ValueError(f"bilinmeyen status: {value!r}")
    return None


def _normalize_evidence(kind: str, value: Any) -> tuple[ValidationStatus, Any]:
    """Tek kanit girdisini (status, detail) ikilisine indirger; uydurmaz."""
    if value is None:
        return ValidationStatus.UNVERIFIED, "girdi verilmedi"
    if isinstance(value, ValidationStatus):
        return value, None
    if isinstance(value, str):
        status = _coerce_status(value)
        if status is None:  # _coerce_status bilinmeyen str icin ValueError yukseltir; mypy daraltmasi
            raise ValueError(f"bilinmeyen status: {value!r}")
        return status, None
    if isinstance(value, Mapping):
        if "status" not in value:
            # status yoksa hukmuz vermek uydurma olur.
            return ValidationStatus.UNVERIFIED, dict(value)
        status = _coerce_status(value["status"])
        if status is None:
            raise ValueError(f"{kind}: status ValidationStatus olmali")
        detail = value.get("detail", None)
        return status, detail
    # Ham UncertaintyReport (duck-typing: to_dict() olan nesne) tek basina
    # hukmuz vermez; ici bos da olsa dolu da olsa UNVERIFIED kalir.
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            raw = to_dict()
        except Exception:  # noqa: BLE001 - yabanci to_dict() her seyi firlatabilir; hukumsuz saymak icin yutulur
            raw = None
        if isinstance(raw, Mapping) and raw and any(
            v for v in raw.values() if v
        ):
            return ValidationStatus.UNVERIFIED, "ham rapor, hukumsuz"
        return ValidationStatus.UNVERIFIED, "bos rapor / veri yok"
    raise TypeError(
        f"{kind}: beklenen girdi ValidationStatus, str, dict veya None; "
        f"alinan {type(value).__name__}"
    )


@dataclass(frozen=True)
class LedgerEntry:
    kind: str
    status: ValidationStatus
    weight: float
    score: float | None = None
    detail: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "status": self.status.value,
            "weight": self.weight,
            "score": self.score,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ConfidenceLedger:
    entries: dict[str, LedgerEntry] = field(default_factory=dict)
    overall_status: ValidationStatus = ValidationStatus.UNVERIFIED
    confidence: float = 0.0
    scored_weight: float = 0.0
    total_weight: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entries": {
                kind: entry.to_dict() for kind, entry in self.entries.items()
            },
            "overall_status": self.overall_status.value,
            "confidence": self.confidence,
            "scored_weight": self.scored_weight,
            "total_weight": self.total_weight,
        }


def _resolve_weights(
    weights: Mapping[str, float] | None,
) -> dict[str, float]:
    resolved = dict(DEFAULT_WEIGHTS)
    if weights:
        for raw_kind, weight in weights.items():
            kind = _normalize_kind(str(raw_kind))
            weight = float(weight)
            if weight < 0:
                raise ValueError(f"{kind}: agirlik negatif olamaz")
            resolved[kind] = weight
    return resolved


def _overall_status(statuses: dict[str, ValidationStatus]) -> ValidationStatus:
    values = [statuses[kind] for kind in EVIDENCE_KINDS]
    if any(s is ValidationStatus.FAIL for s in values):
        return ValidationStatus.FAIL
    if any(s is ValidationStatus.CONFLICT for s in values):
        return ValidationStatus.CONFLICT
    if any(s is ValidationStatus.WARNING for s in values):
        return ValidationStatus.WARNING
    if any(s is ValidationStatus.INCONCLUSIVE for s in values):
        return ValidationStatus.WARNING
    if all(s is ValidationStatus.PASS for s in values):
        return ValidationStatus.PASS
    if all(
        s in (ValidationStatus.TOOL_UNAVAILABLE, ValidationStatus.UNVERIFIED)
        for s in values
    ):
        if all(s is ValidationStatus.TOOL_UNAVAILABLE for s in values):
            return ValidationStatus.TOOL_UNAVAILABLE
        return ValidationStatus.UNVERIFIED
    # Karisik: hukmu verilmis + eksik/kullanilamaz kanit -> tam PASS verilemez.
    return ValidationStatus.UNVERIFIED


def build_ledger(
    symbolic: Any = None,
    numerical: Any = None,
    cross_validation: Any = None,
    falsification: Any = None,
    uncertainty: Any = None,
    weights: Mapping[str, float] | None = None,
    **aliases: Any,
) -> ConfidenceLedger:
    """Bes kanit girdisinden ledger kurar; saf fonksiyondur.

    Eksik girdi (``None``) her zaman ``UNVERIFIED`` sayilir. Skor, yalnizca
    hukmu verilmis girdilerin agirlikli ortalamasidir:

    ``confidence = sum(score_i * w_i) / sum(w_i)`` (skorlananlar uzerinden).
    Sikorlanabilir girdi yoksa ``confidence`` 0.0 olur.
    """
    raw: dict[str, Any] = {
        "symbolic": symbolic,
        "numerical": numerical,
        "cross_validation": cross_validation,
        "falsification": falsification,
        "uncertainty": uncertainty,
    }
    for alias_kind, alias_value in aliases.items():
        kind = _normalize_kind(alias_kind)
        if raw[kind] is not None:
            raise ValueError(f"{kind} iki kez verildi")
        raw[kind] = alias_value

    resolved_weights = _resolve_weights(weights)

    entries: dict[str, LedgerEntry] = {}
    weighted_sum = 0.0
    scored_weight = 0.0
    total_weight = 0.0
    for kind in EVIDENCE_KINDS:
        status, detail = _normalize_evidence(kind, raw[kind])
        weight = resolved_weights[kind]
        score = _SCORES[status]
        total_weight += weight
        if score is not None:
            weighted_sum += score * weight
            scored_weight += weight
        entries[kind] = LedgerEntry(
            kind=kind, status=status, weight=weight, score=score, detail=detail
        )

    confidence = (weighted_sum / scored_weight) if scored_weight > 0 else 0.0
    overall = _overall_status({kind: e.status for kind, e in entries.items()})
    return ConfidenceLedger(
        entries=entries,
        overall_status=overall,
        confidence=confidence,
        scored_weight=scored_weight,
        total_weight=total_weight,
    )
