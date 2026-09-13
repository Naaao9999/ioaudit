import json

import numpy as np

from ioaudit import IOSystem, PriceBasis, TradeFlows, audit, __version__


def test_metadata_completeness_and_provenance():
    io = IOSystem(
        np.array([[0.1]]),
        np.ones(1),
        ["A"],
        metadata={
            "year": 2020,
            "unit": "million_yen",
            "currency": "JPY",
            "price_basis": "producer",
            "valuation": "current",
        },
    )
    first = audit(io)
    second = audit(io)
    assert first.metadata.status == "PASS"
    assert first.metadata.missing_required == []
    assert first.provenance["input_hash"] == second.provenance["input_hash"]
    assert first.provenance["ioaudit_version"] == __version__
    assert first.provenance["requested_numerical_method"] == "auto"
    assert first.provenance["selected_numerical_method"] == "dense"
    assert first.provenance["scale"]["minimum_improvement"] == 0.5
    first.raise_for_status()
    assert first.provenance["thresholds"]["stability.spectral_radius"] == 1.0
    assert "provenance" in json.loads(first.to_json())


def test_provenance_hash_includes_input_side_adjustments():
    base = IOSystem(np.array([[1.0]]), np.array([2.0]), ["A"])
    adjusted = IOSystem(
        np.array([[1.0]]),
        np.array([2.0]),
        ["A"],
        input_adjustments=np.array([3.0]),
    )
    assert audit(base).provenance["input_hash"] != audit(adjusted).provenance["input_hash"]


def test_price_basis_is_typed_and_serialized_as_its_machine_value():
    io = IOSystem(
        np.array([[0.1]]),
        np.ones(1),
        ["A"],
        metadata={
            "year": 2020,
            "unit": "million_yen",
            "price_basis": PriceBasis.PRODUCER,
        },
    )

    report = audit(io)

    assert report.metadata.price_basis is PriceBasis.PRODUCER
    assert report.metadata.price_basis_status == "DECLARED"
    assert report.metadata.values["price_basis"] == "producer"
    assert json.loads(report.to_json())["metadata"]["price_basis"] == "producer"


def test_price_basis_unknown_is_explicit_but_valid():
    io = IOSystem(
        np.array([[0.1]]),
        np.ones(1),
        ["A"],
        metadata={
            "year": 2020,
            "unit": "million_yen",
            "price_basis": "unknown",
        },
    )

    report = audit(io)

    assert report.metadata.status == "WARNING"
    assert report.metadata.price_basis is PriceBasis.UNKNOWN
    assert report.metadata.price_basis_status == "UNKNOWN"


def test_invalid_price_basis_is_reported_without_inference():
    io = IOSystem(
        np.array([[0.1]]),
        np.ones(1),
        ["A"],
        metadata={
            "year": 2020,
            "unit": "million_yen",
            "price_basis": "market_price",
        },
    )

    report = audit(io)

    assert report.metadata.status == "WARNING"
    assert report.metadata.price_basis is None
    assert report.metadata.price_basis_status == "INVALID"
    assert report.metadata.invalid_fields == ["price_basis"]
