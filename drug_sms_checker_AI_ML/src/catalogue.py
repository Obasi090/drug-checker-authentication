"""Read-only local medicine catalogue loading and in-memory derivation.

This module never writes to ``data/test_drugs.csv`` and never contacts an
external service. It preserves the six source columns verbatim in each
``CatalogueProduct.original`` mapping, keeps blanks missing, and derives
comparison keys and limited structured fields in memory only.

Derived fields are deliberately conservative:

- strength is parsed only when an explicit supported unit is present;
- package volume is parsed separately and is never treated as strength;
- dosage form and ingredient keys are derived only from text that exists in
  the source row.
"""

from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .message import normalize
from .photo import is_missing

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOGUE_PATH = ROOT / "data" / "test_drugs.csv"

EXPECTED_COLUMNS = (
    "brand_name",
    "generic_name",
    "registration_number",
    "applicant_name",
    "manufacturer",
    "source_url",
)
REQUIRED_VALUES = ("brand_name", "generic_name", "registration_number", "source_url")

_GREEK_TRANSLITERATION = str.maketrans({
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "δ": "delta",
})

_STRENGTH_TOKEN_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?|\.\d+)\s*"
    r"(?P<unit>mcg|μg|micrograms?|mg/ml|mg\s*/\s*ml|"
    r"milligrams?\s+per\s+millilit(?:er|re)s?|mg|milligrams?|"
    r"g|grams?|iu|i\.?\s*u\.?|units?|%|percent)",
    re.IGNORECASE,
)
_VOLUME_TOKEN_RE = re.compile(
    r"(?P<value>\d+(?:\.\d+)?|\.\d+)\s*"
    r"(?P<unit>ml|millilit(?:er|re)s?|l|lit(?:er|re)s?)",
    re.IGNORECASE,
)

_MASS_FACTORS_TO_MCG = {
    "mcg": Decimal("1"),
    "mg": Decimal("1000"),
    "g": Decimal("1000000"),
}


class CatalogueError(ValueError):
    """Raised when the local catalogue is missing required or valid data."""


@dataclass(frozen=True)
class StrengthComponent:
    """One parsed numeric strength component with an explicit unit."""

    value: str
    unit: str
    base_value: str
    base_unit: str


@dataclass(frozen=True)
class ParsedStrength:
    raw: str
    parsed: bool
    components: tuple[StrengthComponent, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class VolumeComponent:
    """One parsed package-volume component."""

    value: str
    unit: str
    base_value_ml: str


@dataclass(frozen=True)
class ParsedVolume:
    raw: str
    parsed: bool
    components: tuple[VolumeComponent, ...] = ()
    note: str = ""


def blank_to_none(value: str | None) -> str | None:
    """Return stripped text, or None for blank/missing-token values."""
    if value is None:
        return None
    text = str(value).strip()
    return None if is_missing(text) else text


def registration_key(value: str | None) -> str:
    """Exact-match key: case and hyphen glyphs are safe to normalise.

    Nothing else is changed. Registration numbers are never fuzzy-matched.
    """
    if value is None or is_missing(value):
        return ""
    return normalize(str(value)).strip()


def brand_key(value: str | None) -> str:
    """Conservative brand key: case, whitespace and punctuation boundaries."""
    if value is None or is_missing(value):
        return ""
    text = normalize(str(value))
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def generic_key(value: str | None) -> str:
    """Ingredient-set key that preserves multi-ingredient information.

    Semicolon-separated ingredients are treated as a set, sorted so that
    ingredient order does not create a false mismatch. Greek alpha/beta
    characters are transliterated to ASCII names. Parenthetical salt text is
    retained rather than guessed away.
    """
    if value is None or is_missing(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).translate(_GREEK_TRANSLITERATION)
    parts: list[str] = []
    for part in re.split(r"[;\n]+", text.casefold()):
        part = re.sub(r"[^\w\s]", " ", part, flags=re.UNICODE)
        part = re.sub(r"\s+", " ", part).strip()
        if part:
            parts.append(part)
    return " | ".join(sorted(parts))


def _canonical_strength_unit(raw: str) -> tuple[str, str, str]:
    """Return (display_unit, base_unit, factor-to-base as string)."""
    token = re.sub(r"\s+", "", unicodedata.normalize("NFKC", raw).casefold()).strip(".")
    if token in {"mcg", "μg", "microgram", "micrograms"}:
        return "mcg", "mcg", "1"
    if token in {"mg", "milligram", "milligrams"}:
        return "mg", "mcg", "1000"
    if token in {"g", "gram", "grams"}:
        return "g", "mcg", "1000000"
    if token in {"mg/ml", "milligrampermilliliter", "milligrampermillilitre"}:
        return "mg/ml", "mg/ml", "1"
    if token in {"iu", "i.u", "unit", "units"}:
        return "IU", "IU", "1"
    if token in {"%", "percent"}:
        return "%", "%", "1"
    return token or "unknown", token or "unknown", "1"


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def parse_strength_text(value: str | None) -> ParsedStrength:
    """Parse explicit numeric strength tokens; never infer a missing unit.

    Supported mass units (mcg/mg/g) are convertible to a canonical mcg base.
    IU, %, mg/ml and unknown units are kept distinct because no safe
    conversion is available. Volume-only text such as ``100 ml`` is not a
    strength and therefore remains unparsed.
    """
    if value is None or is_missing(value):
        return ParsedStrength(raw="", parsed=False, note="strength value is missing")
    raw = unicodedata.normalize("NFKC", str(value)).strip()
    matches = list(_STRENGTH_TOKEN_RE.finditer(raw))
    if not matches:
        return ParsedStrength(
            raw=raw,
            parsed=False,
            note="no supported numeric strength with an explicit unit was found",
        )

    components: list[StrengthComponent] = []
    for match in matches:
        try:
            amount = Decimal(match.group("value"))
        except InvalidOperation:
            continue
        unit, base_unit, factor = _canonical_strength_unit(match.group("unit"))
        components.append(StrengthComponent(
            value=_decimal_text(amount),
            unit=unit,
            base_value=_decimal_text(amount * Decimal(factor)),
            base_unit=base_unit,
        ))

    if not components:
        return ParsedStrength(raw=raw, parsed=False, note="strength numbers were not parseable")
    return ParsedStrength(
        raw=raw,
        parsed=True,
        components=tuple(components),
        note="parsed numeric strength components; unmatched text is preserved in raw",
    )


def strength_display(parsed: ParsedStrength) -> str | None:
    """Human-readable derived strength text, or None when unparsed."""
    if not parsed.parsed or not parsed.components:
        return None
    return " / ".join(f"{item.value} {item.unit}" for item in parsed.components)


def _canonical_volume_unit(raw: str) -> str:
    token = re.sub(r"\s+", "", unicodedata.normalize("NFKC", raw).casefold())
    if token in {"l", "liter", "liters", "litre", "litres"}:
        return "l"
    return "ml"


def parse_volume_text(value: str | None) -> ParsedVolume:
    """Parse numeric package-volume tokens independently of strength."""
    if value is None or is_missing(value):
        return ParsedVolume(raw="", parsed=False, note="volume value is missing")
    raw = unicodedata.normalize("NFKC", str(value)).strip()
    matches = list(_VOLUME_TOKEN_RE.finditer(raw))
    if not matches:
        return ParsedVolume(
            raw=raw,
            parsed=False,
            note="no supported numeric volume with an explicit unit was found",
        )

    components: list[VolumeComponent] = []
    for match in matches:
        try:
            amount = Decimal(match.group("value"))
        except InvalidOperation:
            continue
        unit = _canonical_volume_unit(match.group("unit"))
        base_ml = amount * (Decimal("1000") if unit == "l" else Decimal("1"))
        components.append(VolumeComponent(
            value=_decimal_text(amount),
            unit=unit,
            base_value_ml=_decimal_text(base_ml),
        ))
    if not components:
        return ParsedVolume(raw=raw, parsed=False, note="volume numbers were not parseable")
    return ParsedVolume(raw=raw, parsed=True, components=tuple(components))


def volume_display(parsed: ParsedVolume) -> str | None:
    if not parsed.parsed or not parsed.components:
        return None
    return " / ".join(f"{item.value} {item.unit}" for item in parsed.components)


_FORM_PATTERNS: tuple[tuple[str, str], ...] = (
    ("water_for_injection", r"\bwater\s+for\s+injection\b"),
    ("eye_drops", r"\beye\s+drops?\b"),
    ("dispersible_tablet", r"\bdispersible\s+tablets?\b"),
    ("tablet", r"\btablets?\b"),
    ("capsule", r"\bcapsules?\b"),
    ("injection", r"\binjections?\b"),
    ("cream", r"\bcreams?\b"),
    ("suspension", r"\bsuspensions?\b"),
    ("emulsion", r"\bemulsions?\b"),
    ("ointment", r"\bointments?\b"),
    ("syrup", r"\bsyrups?\b"),
    ("drops", r"\bdrops?\b"),
    ("solution", r"\bsolutions?\b"),
)


def derive_dosage_forms(value: str | None) -> tuple[str, ...]:
    """Derive only dosage forms explicitly written in the supplied text."""
    if value is None or is_missing(value):
        return ()
    text = normalize(str(value))
    found: list[str] = []
    for form, pattern in _FORM_PATTERNS:
        if re.search(pattern, text):
            found.append(form)
    if "dispersible_tablet" in found and "tablet" in found:
        found.remove("tablet")
    if "water_for_injection" in found and "injection" in found:
        found.remove("injection")
    if "eye_drops" in found and "drops" in found:
        found.remove("drops")
    return tuple(found)


class CatalogueProduct(BaseModel):
    """One read-only source row plus in-memory derived fields."""

    model_config = ConfigDict(extra="forbid")

    product_id: str
    row_number: int
    brand_name: str
    generic_name: str | None = None
    registration_number: str
    applicant_name: str | None = None
    manufacturer: str | None = None
    source_url: str | None = None
    original: dict[str, str] = Field(default_factory=dict)

    brand_key: str
    generic_key: str
    registration_key: str

    derived_strength: str | None = None
    derived_dosage_forms: tuple[str, ...] = ()
    derived_package_volume: str | None = None

    @property
    def identity_label(self) -> str:
        return f"{self.brand_name} [{self.registration_number}]"


class MedicineCatalogue(BaseModel):
    """In-memory indexes over the local read-only catalogue."""

    model_config = ConfigDict(extra="forbid")

    products: tuple[CatalogueProduct, ...]
    source_path: str
    source_sha256: str
    registration_index: dict[str, CatalogueProduct] = Field(default_factory=dict)
    brand_index: dict[str, list[CatalogueProduct]] = Field(default_factory=dict)
    generic_index: dict[str, list[CatalogueProduct]] = Field(default_factory=dict)

    def registration_lookup(self, value: str | None) -> CatalogueProduct | None:
        return self.registration_index.get(registration_key(value) or "")

    def brand_lookup(self, value: str | None) -> list[CatalogueProduct]:
        return list(self.brand_index.get(brand_key(value) or "", []))

    def generic_lookup(self, value: str | None) -> list[CatalogueProduct]:
        return list(self.generic_index.get(generic_key(value) or "", []))

    @property
    def brand_names(self) -> list[str]:
        return [product.brand_name for product in self.products]


def load_catalogue(path: str | Path | None = None) -> MedicineCatalogue:
    """Load and validate the local catalogue without modifying it."""
    source = Path(path) if path is not None else DEFAULT_CATALOGUE_PATH
    if not source.is_file():
        raise CatalogueError(f"catalogue file does not exist: {source}")

    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or [])
        missing_columns = [name for name in EXPECTED_COLUMNS if name not in header]
        if missing_columns:
            raise CatalogueError(f"catalogue is missing columns: {', '.join(missing_columns)}")
        rows = list(reader)

    products: list[CatalogueProduct] = []
    registration_index: dict[str, CatalogueProduct] = {}
    brand_index: dict[str, list[CatalogueProduct]] = defaultdict(list)
    generic_index: dict[str, list[CatalogueProduct]] = defaultdict(list)

    for offset, row in enumerate(rows, start=2):
        for field in REQUIRED_VALUES:
            if not blank_to_none(row.get(field)):
                raise CatalogueError(f"row {offset}: required field {field!r} is blank")

        original = {name: str(row.get(name, "") or "") for name in header}
        brand = str(row["brand_name"]).strip()
        generic = blank_to_none(row.get("generic_name"))
        registration = str(row["registration_number"]).strip()
        reg_key = registration_key(registration)
        if not reg_key:
            raise CatalogueError(f"row {offset}: registration number is not usable")
        if reg_key in registration_index:
            raise CatalogueError(
                f"row {offset}: duplicate registration number "
                f"{registration!r} (first seen in {registration_index[reg_key].product_id})"
            )

        parsed_strength = parse_strength_text(brand)
        parsed_volume = parse_volume_text(brand)
        product = CatalogueProduct(
            product_id=f"CAT-{offset - 1:04d}",
            row_number=offset,
            brand_name=brand,
            generic_name=generic,
            registration_number=registration,
            applicant_name=blank_to_none(row.get("applicant_name")),
            manufacturer=blank_to_none(row.get("manufacturer")),
            source_url=blank_to_none(row.get("source_url")),
            original=original,
            brand_key=brand_key(brand),
            generic_key=generic_key(generic),
            registration_key=reg_key,
            derived_strength=strength_display(parsed_strength),
            derived_dosage_forms=derive_dosage_forms(brand),
            derived_package_volume=volume_display(parsed_volume),
        )
        products.append(product)
        registration_index[reg_key] = product
        if product.brand_key:
            brand_index[product.brand_key].append(product)
        if product.generic_key:
            generic_index[product.generic_key].append(product)

    if not products:
        raise CatalogueError("catalogue contains no medicine records")

    return MedicineCatalogue(
        products=tuple(products),
        source_path=str(source),
        source_sha256=source_hash,
        registration_index=registration_index,
        brand_index=dict(brand_index),
        generic_index=dict(generic_index),
    )
