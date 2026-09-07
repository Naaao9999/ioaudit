import json

import numpy as np

from ioaudit import IOSystem, audit


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
    assert first.provenance["ioaudit_version"] == "0.1.0"
    assert first.provenance["requested_numerical_method"] == "auto"
    assert first.provenance["selected_numerical_method"] == "dense"
    assert first.provenance["scale"]["minimum_improvement"] == 0.5
    first.raise_for_status()
    assert first.provenance["thresholds"]["stability.spectral_radius"] == 1.0
    assert "provenance" in json.loads(first.to_json())
