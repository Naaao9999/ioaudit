"""Bilingual non-sector evidence uses exact normalized labels, not translation."""

import numpy as np
import pandas as pd
import pytest

from ioaudit import IOSystem, audit


@pytest.mark.parametrize("label", [
    "最終需要", "家計消費", "政府消費", "固定資本形成", "在庫",
    "輸入", "輸出", "移入", "移出", "付加価値", "雇用者所得",
    "final demand", "household consumption", "government consumption",
    "household final consumption expenditure",
    "government final consumption expenditure", "gross fixed capital formation",
    "changes in inventories", "imports", "exports", "interregional inflows",
    "interregional outflows", "gross value added", "compensation of employees",
    "operating surplus", "taxes less subsidies on products",
    "labour compensation", "labor compensation", "  VALUE　ADDED  ",
    "ＩＭＰＯＲＴＳ",
    "Final consumption expenditure",
    "Final consumption expenditure by government",
    "Final consumption expenditure by households",
    "Final consumption expenditure by non-profit organisations serving households (NPISH)",
    "Private final consumption expenditure (Households and NPISH)",
    "Private gross fixed capital formation",
    "Government gross fixed capital formation",
    "Acquisitions less disposals of valuables",
    "Exports of goods to EU",
    "Exports of goods to rest of the world",
    "Exports of services",
    "Use of imported products, cif",
    "Total intermediate demand",
    "Total intermediate input",
    "Total intermediate use at purchaser's prices",
    "Total final demand",
    "Total demand",
    "Total output at basic prices",
    "Gross domestic output",
    "Total supply",
    "Total input",
    "Gross operating surplus and mixed income",
    "Net operating surplus",
    "Consumption of fixed capital",
    "Trade margins",
    "Transport margins",
    "Taxes less subsidies on production",
    "Taxes on products (Imports)",
    "Imports and related taxes",
    "Taxes on production and products less subsidies",
    "Total value added",
])
def test_bilingual_nonsector_labels_are_warning_evidence(label):
    labels = ["sector A", label]
    z = pd.DataFrame([[0.1, 0.02], [0.03, 0.2]], index=labels, columns=labels)
    original = z.copy(deep=True)
    report = audit(IOSystem(z, np.ones(2), labels))
    for candidates in (report.structure.possible_nonsector_rows,
                       report.structure.possible_nonsector_columns):
        assert len(candidates) == 1
        assert candidates[0]["label"] == label
        assert candidates[0]["severity"] == "WARNING"
    assert report.structure.status == "PASS"
    assert report.coefficients.status == "PASS"
    pd.testing.assert_frame_equal(z, original)


@pytest.mark.parametrize("label", [
    "Imports handling services", "Investment banking", "Total logistics",
    "輸入関連サービス", "Agriculture", "農業",
])
def test_nonsector_words_inside_sector_names_do_not_match(label):
    labels = ["sector A", label]
    z = pd.DataFrame([[0.1, 0.02], [0.03, 0.2]], index=labels, columns=labels)
    report = audit(IOSystem(z, np.ones(2), labels))
    assert report.structure.possible_nonsector_rows == []
    assert report.structure.possible_nonsector_columns == []
