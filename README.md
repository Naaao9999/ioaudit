# ioaudit

**Preflight diagnostics for input-output tables.**

[日本語](README.ja.md)

`ioaudit` is a Python library for checking input-output tables **before** they are passed to analytical code.

It audits data structure, accounting consistency, matrix orientation, zero-output sectors, possible subtotal double counting, powers-of-ten scale errors, and numerical stability in Leontief systems.

> **Diagnose, do not repair.**

`ioaudit` reports problems and ambiguity, but it does not silently transpose, rebalance, delete, rescale, or otherwise repair the supplied table. When required information is unavailable, the affected diagnostic is reported as `SKIPPED` rather than inferred.

---

## Quickstart

At minimum, an audit requires a transaction matrix `Z`, an output vector `x`, and sector identifiers.

```python
import numpy as np

from ioaudit import IOSystem, audit

Z = np.array([
    [10.0, 2.0],
    [3.0, 8.0],
])

x = np.array([18.0, 18.0])

io = IOSystem(
    Z=Z,
    x=x,
    sectors=["agriculture", "manufacturing"],
)

report = audit(io)
print(report.summary())
```

Individual diagnostics are available through the returned `AuditReport`:

```python
report.structure
report.orientation
report.accounting
report.zero_output
report.coefficients
report.stability
report.scale
report.components
report.metadata
report.provenance
```

---

## What does ioaudit check?

Depending on the available inputs, `audit()` evaluates the following areas.

### Structure

- whether `Z` is two-dimensional and square
- whether `x` and sector dimensions are aligned
- NaN, Inf, and non-numeric values
- row, column, and sector-label alignment
- duplicate labels
- duplicates revealed after Unicode and whitespace normalization
- possible total rows, total columns, and non-sector content in `Z`
- exact duplicate rows and columns

### Orientation

- row/column label consistency
- sector ordering
- alignment of `x`
- accounting evidence under the supplied orientation versus the transpose
- `possible_transpose`

A possible transpose is reported as evidence only. The matrix is never transposed automatically.

### Accounting consistency

When `Y`, `V`, and an explicit accounting convention are available, `ioaudit` can calculate input- and output-side accounting residuals, including:

- sector-level residuals
- absolute residuals
- relative residuals
- MAE
- RMSE
- maximum residuals
- rounding-aware status

### Zero-output and zero-structure diagnostics

- zero-output sectors
- all-zero rows
- all-zero columns
- isolated sectors
- inconsistencies between zero output and transaction structure

### Technical coefficients and Leontief stability

- technical coefficient matrix `A`
- coefficient finiteness
- spectral radius
- invertibility of `I - A`
- condition number
- finiteness of the Leontief inverse

### Possible subtotal double counting

`report.components` checks whether columns in `Y` or rows in `V` appear to be totals or subtotals that may already include other supplied components.

```python
report.components.possible_subtotal_columns
report.components.possible_subtotal_rows
report.components.double_count_risk
```

Candidates are not removed automatically. If a possible subtotal makes the correct accounting subset ambiguous, the affected balance is reported as `SKIPPED`.

### Powers-of-ten scale errors

`report.scale` uses available accounting residuals to look for possible powers-of-ten scale mistakes in:

- `x`
- `Z`
- `Y`
- `V`
- individual rows of `Z`
- individual columns of `Z`
- individual cells of `Z`

```python
for candidate in report.scale.possible_cell_scale_errors:
    print(
        candidate["row"],
        candidate["column"],
        candidate["candidate_factor"],
    )
```

A scale candidate is diagnostic evidence, not a correction. `ioaudit` never applies the suggested factor to the source data.

---

## Accounting conventions

Accounting identities are evaluated only under an explicitly declared interpretation of the table.

The plain constructor is intentionally conservative:

```python
from ioaudit import AccountingConvention

accounting = AccountingConvention()
```

Its semantic fields default to `"unknown"`. This means affected accounting checks are `SKIPPED` instead of assuming a particular national or statistical-office convention.

For common accounting structures, explicit presets are available:

```python
accounting = AccountingConvention.domestic_competitive(
    inflow_sign="negative",
    trade_representation="outflows_in_Y",
)
```

Other presets include:

```python
AccountingConvention.domestic_noncompetitive()
AccountingConvention.total_transactions()
```

These presets describe accounting structures, not countries.

A fully explicit convention can also be supplied:

```python
accounting = AccountingConvention(
    transaction_scope="domestic",
    import_treatment="competitive",
    trade_representation="embedded",
    external_flow_scope="international",
    inflow_sign="negative",
    outflow_sign="positive",
)
```

Then use it when constructing the IO system:

```python
io = IOSystem(
    Z=Z,
    x=x,
    sectors=["agriculture", "manufacturing"],
    Y=np.array([[6.0], [7.0]]),
    V=np.array([[5.0, 8.0]]),
    accounting=accounting,
)

report = audit(io)
```

`ioaudit` does not infer import treatment or trade representation merely from the presence of an import vector.

---

## Rounding tolerance

Published input-output tables may contain residuals caused by rounding. Tolerances can be declared explicitly:

```python
report = audit(
    io,
    accounting_tolerance={
        "absolute": 1.0,
        "relative": 1e-6,
        "rounding_unit": 1.0,
    },
)
```

A non-zero residual within the declared tolerance is reported as `ROUNDING_LEVEL`.

The selected tolerance is stored in the report provenance. Input values are never changed.

---

## Trade flows

External and interregional flows can be represented with `TradeFlows`.

```python
from ioaudit import TradeFlows

trade = TradeFlows(
    interregional_inflows=interregional_inflows,
    international_imports=imports,
    interregional_outflows=interregional_outflows,
    international_exports=exports,
)
```

If only combined flows are available:

```python
trade = TradeFlows(
    combined_inflows=inflows,
    combined_outflows=outflows,
)
```

`AccountingConvention` declares whether trade is embedded in final demand, included as outflows in `Y`, reported separately, or unknown.

`ioaudit` never infers this relationship. Conflicting combined and split representations are reported rather than added together.

Trade vectors are treated as supply/demand-side flows. They are not reused as user-specific intermediate inputs unless such information is explicitly available.

---

## Reference validation

Externally calculated technical-coefficient or Leontief-inverse matrices can be supplied as references:

```python
io = IOSystem(
    Z=Z,
    x=x,
    sectors=sectors,
    A_reference=A_ref,
    L_reference=L_ref,
)
```

`ioaudit` compares the internally calculated matrices with the supplied references and reports structural and numerical differences.

---

## Metadata and provenance

Metadata can be attached to the input table so that its interpretation remains reproducible:

```python
io = IOSystem(
    Z=Z,
    x=x,
    sectors=sectors,
    metadata={
        "year": 2020,
        "unit": "million_yen",
        "currency": "JPY",
        "price_basis": "producer",
        "valuation": "current",
    },
)
```

The metadata diagnostic checks fields such as:

- `year`
- `unit`
- `price_basis`
- `currency`
- `valuation`

Each audit also includes `report.provenance`, which records information such as:

- ioaudit version
- SHA-256 input hash
- requested numerical method
- selected numerical method
- accounting tolerance
- scale-diagnostic settings
- applied thresholds
- audit timestamp

---

## File diagnostics

Delimited text files can be inspected before constructing an `IOSystem`.

```python
from ioaudit import inspect_csv

raw_report = inspect_csv(
    "io.csv",
    delimiter=",",
    encoding="cp932",
)

print(raw_report.summary())
```

The file-level diagnostics can report issues such as:

- encoding and BOM
- delimiter problems
- empty rows
- inconsistent column counts
- empty or duplicate headers
- trailing delimiters
- malformed quoting
- suspicious whitespace
- non-numeric tokens
- NaN/Inf-like tokens
- likely unquoted thousands separators
- note rows
- repeated headers within the file

`ioaudit` does not automatically infer which regions of a file correspond to `Z`, `x`, `Y`, or `V`, and it does not remove footnotes or total rows automatically.

```text
file diagnostics
    ↓
parsing by the caller
    ↓
IOSystem
    ↓
audit()
```

---

## Using the report

Reports can be inspected interactively or exported for downstream processing:

```python
report.summary()
report.to_dict()
report.to_json()
report.to_dataframe()
```

For automated checks or CI:

```python
report.raise_for_status()
```

An explicit accounting-residual threshold can also be applied:

```python
report.raise_for_status(
    max_relative_residual=1e-4,
)
```

---

## Numerical routes

```python
report = audit(io, numerical_method="auto")
```

With `"auto"`, `ioaudit` selects a dense or iterative numerical route according to the input size and whether the matrix is sparse. The selected route and approximation metadata are recorded in `report.methods` and provenance.

---

## Design principle

### Diagnose, do not repair

`ioaudit` does **not** automatically:

- balance inconsistent tables
- remove totals or subtotal rows
- transpose matrices
- change signs
- rescale suspicious values
- infer unknown accounting conventions

Audit results are evidence for pre-analysis review, not instructions to mutate the table.

---

## Scope

Version 0.1 focuses on **preflight diagnostics for a single input-output system**.

It does not provide:

- RAS / GRAS / KRAS
- matrix balancing
- automatic table repair
- regionalization
- trade estimation
- data downloading
- automatic Excel interpretation
- automatic sector matching
- table comparison
- hierarchy or aggregation diagnostics
- impact analysis
- multiplier analysis
- structural decomposition analysis
- policy ranking
- visualization
- GUI tools

`ioaudit` is not an input-output analysis package.

**It answers a narrower question: is this table safe to pass to analytical code?**

---

## Installation

For the current development version, clone the repository and install it locally:

```bash
pip install -e .
```

Python 3.10 or later is required.

To include test dependencies:

```bash
pip install -e ".[test]"
```

---

## Tests

```bash
pytest
```

---

## License

MIT License.
