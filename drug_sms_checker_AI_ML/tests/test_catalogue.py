"""Read-only catalogue loading, validation, indexing and parsing tests."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from conftest import CATALOGUE_CSV
from src.catalogue import (
    EXPECTED_COLUMNS,
    CatalogueError,
    load_catalogue,
    parse_strength_text,
    parse_volume_text,
)


def _write_catalogue(tmp_path: Path, rows: list[dict[str, str]],
                     columns: list[str] | None = None) -> Path:
    path = tmp_path / "catalogue.csv"
    fieldnames = columns or list(EXPECTED_COLUMNS)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            {name: row.get(name, "") for name in fieldnames}
            for row in rows
        )
    return path


def _row(**overrides: str) -> dict[str, str]:
    row = {name: "value" for name in EXPECTED_COLUMNS}
    row.update({
        "brand_name": "Test Brand 100 mg Tablet",
        "generic_name": "Test Generic",
        "registration_number": "A1-0001",
        "applicant_name": "Applicant Ltd",
        "manufacturer": "",
        "source_url": "https://example.invalid/record/1",
    })
    row.update(overrides)
    return row


def test_default_catalogue_has_40_records_and_all_source_columns() -> None:
    catalogue = load_catalogue(CATALOGUE_CSV)

    assert len(catalogue.products) == 40
    assert len(catalogue.registration_index) == 40
    for product in catalogue.products:
        assert tuple(product.original.keys()) == EXPECTED_COLUMNS
        assert product.source_url


def test_source_csv_is_not_modified_by_loading() -> None:
    before = CATALOGUE_CSV.read_bytes()
    load_catalogue(CATALOGUE_CSV)
    assert CATALOGUE_CSV.read_bytes() == before


def test_original_values_preserved_and_blanks_are_missing() -> None:
    catalogue = load_catalogue(CATALOGUE_CSV)
    product = catalogue.registration_lookup("B4-1180")

    assert product is not None
    assert product.original["brand_name"] == "1980 Azithromycin USP 250 mg Tablets"
    assert product.original["registration_number"] == "B4-1180"
    assert product.original["applicant_name"] == "1980 Pharmaceutical Limited"
    assert product.original["manufacturer"] == "Surmount Laboratories Pvt Ltd"
    assert product.manufacturer == "Surmount Laboratories Pvt Ltd"

    no_manufacturer = catalogue.registration_lookup("B4-9460")
    assert no_manufacturer is not None
    assert no_manufacturer.original["manufacturer"] == ""
    assert no_manufacturer.manufacturer is None
    assert no_manufacturer.applicant_name == "Micro Nova Pharmaceuticals Ind Ltd"


def test_applicant_is_never_used_as_manufacturer(tmp_path: Path) -> None:
    path = _write_catalogue(tmp_path, [_row()])
    product = load_catalogue(path).products[0]

    assert product.applicant_name == "Applicant Ltd"
    assert product.manufacturer is None


def test_exact_indexes_use_only_safe_normalisation() -> None:
    catalogue = load_catalogue(CATALOGUE_CSV)

    by_registration = catalogue.registration_lookup("b4‐1180")
    assert by_registration is not None
    assert by_registration.registration_number == "B4-1180"

    brand_hits = catalogue.brand_lookup("AC MOL DROPS")
    assert [item.registration_number for item in brand_hits] == ["A11-0131"]

    paracetamol = catalogue.generic_lookup("Paracetamol")
    assert {item.registration_number for item in paracetamol} == {"A11-0131", "A4-0704"}
    assert len(paracetamol) == 2

    arteether = catalogue.generic_lookup("α-β Arteether")
    assert len(arteether) == 4
    assert {item.registration_number for item in arteether} == {
        "A4-100942", "A4-101076", "B4-7301", "B4-7300",
    }


def test_catalogue_validation_rejects_missing_required_value(tmp_path: Path) -> None:
    path = _write_catalogue(tmp_path, [_row(source_url="")])
    with pytest.raises(CatalogueError, match="required field 'source_url' is blank"):
        load_catalogue(path)


def test_catalogue_validation_rejects_duplicate_registration(tmp_path: Path) -> None:
    path = _write_catalogue(tmp_path, [_row(), _row(brand_name="Other Brand")])
    with pytest.raises(CatalogueError, match="duplicate registration number"):
        load_catalogue(path)


def test_catalogue_validation_rejects_missing_column(tmp_path: Path) -> None:
    columns = [name for name in EXPECTED_COLUMNS if name != "manufacturer"]
    path = _write_catalogue(tmp_path, [_row()], columns=columns)
    with pytest.raises(CatalogueError, match="missing columns: manufacturer"):
        load_catalogue(path)


def test_strength_parser_keeps_strength_and_volume_separate() -> None:
    strength = parse_strength_text("250 mg")
    assert strength.parsed
    assert strength.components[0].value == "250"
    assert strength.components[0].unit == "mg"
    assert strength.components[0].base_unit == "mcg"
    assert strength.components[0].base_value == "250000"

    volume_only = parse_strength_text("100 ml")
    assert volume_only.parsed is False
    assert "explicit unit" in volume_only.note

    volume = parse_volume_text("100 ml")
    assert volume.parsed
    assert volume.components[0].base_value_ml == "100"

    litres = parse_volume_text("1 L")
    assert litres.parsed
    assert litres.components[0].base_value_ml == "1000"


def test_catalogue_derives_strength_and_volume_from_existing_text_only() -> None:
    catalogue = load_catalogue(CATALOGUE_CSV)

    aciclovir = catalogue.registration_lookup("A4-100450")
    assert aciclovir is not None
    assert aciclovir.derived_strength == "5 %"
    assert aciclovir.derived_package_volume is None

    dextrose = catalogue.registration_lookup("04-0858")
    assert dextrose is not None
    assert dextrose.derived_strength == "10 %"
    assert dextrose.derived_package_volume == "1000 ml"
    assert "500/1000 mL" in dextrose.brand_name
