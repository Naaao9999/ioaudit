# ioaudit

**産業連関表を分析する前に、表そのものを監査する Python ライブラリ。**  
**Preflight diagnostics for input-output tables.**

[日本語](#日本語) | [English](#english)

---

# 日本語

`ioaudit` は、産業連関表を分析コードに渡す**前**に、データ構造、会計整合性、行列の向き、ゼロ産出部門、合計列・行の混入、桁・単位ミスの候補、Leontief 系の数値安定性などを診断する Python ライブラリです。

> **Diagnose, do not repair. — 診断するが、自動修正しない。**

問題が見つかっても、`ioaudit` は表を勝手に転置・補正・削除・再スケールしません。必要な情報が不足している診断は、値や会計規約を推測せず `SKIPPED` として扱います。

## Quickstart

最低限、取引行列 `Z`、産出額 `x`、部門名 `sectors` があれば監査できます。

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
    sectors=["農業", "製造業"],
)

report = audit(io)
print(report.summary())
```

個別の診断結果には、次のようにアクセスできます。

```python
report.structure
report.orientation
report.accounting
report.zero_output
report.coefficients
report.stability
report.reference
report.signs
report.scale
report.components
report.metadata
report.provenance
```

## 診断ステータス

`ioaudit` は、診断結果を単純な真偽値だけで表しません。

- `PASS`: 指定された条件の範囲で問題が確認されなかった
- `FAIL`: 明示的な不整合または設定した閾値違反が確認された
- `WARNING`: 確認すべき候補や証拠がある
- `SKIPPED`: 必要な情報が不足しており、安全に判定できない
- `ROUNDING_LEVEL`: 非ゼロ残差が、明示した丸め許容範囲内にある

`SKIPPED` は「問題なし」を意味しません。`ioaudit` が推測を避けたことを意味します。

## 何を診断するか

### 構造

- `Z` が2次元・正方行列か
- `x` と部門数が整合しているか
- NaN / Inf / 非数値が含まれていないか
- 行・列・部門ラベルが整合しているか
- 重複ラベルがないか
- Unicode幅・空白を正規化した後に重複が生じないか
- 合計行・合計列や非部門項目らしきラベルが `Z` に混入していないか
- 完全一致する行・列がないか

### 行列の向き

- 行ラベルと列ラベルの対応
- 部門順序
- `x` のalignment
- 現在の向きと転置した場合の会計残差比較
- `possible_transpose`

転置の可能性を報告しても、行列を自動的に転置することはありません。

### 会計整合性

`Y`、`V` と会計規約が利用できる場合、投入側・産出側の会計残差を診断します。

- sector-level residual
- absolute residual
- relative residual
- MAE
- RMSE
- maximum residual
- rounding-aware status

### ゼロ産出・ゼロ構造

- ゼロ産出部門
- 全ゼロ行
- 全ゼロ列
- 孤立部門
- ゼロ産出と取引構造の不整合

### 投入係数・Leontief 系

技術係数行列

```text
A = Z diag(x)^(-1)
```

を安全に構成し、次を診断します。

- 係数の有限性
- coefficient sums
- spectral radius
- `I - A` の可逆性
- condition number
- Leontief inverse の有限性

### 合計列・合計行の二重計上候補

`report.components` は、`Y` の最終需要計や `V` の付加価値計など、他の構成要素をすでに含んでいる可能性がある列・行を診断します。

```python
report.components.possible_subtotal_columns
report.components.possible_subtotal_rows
report.components.double_count_risk
```

候補を自動的に除外することはありません。正しい構成要素の選択が曖昧な場合、影響する会計診断は `SKIPPED` になります。

### 桁・単位ミスの候補

`report.scale` は、利用可能な会計残差を使って10のべき乗による桁違いの候補を探索します。

対象は、

- `x` 全体
- `Z` 全体
- `Y` 全体
- `V` 全体
- `Z` の行
- `Z` の列
- `Z` のセル

です。

```python
for candidate in report.scale.possible_cell_scale_errors:
    print(
        candidate["row"],
        candidate["column"],
        candidate["candidate_factor"],
    )
```

scale candidate は修正値ではなく、残差改善にもとづく診断上の証拠です。`ioaudit` が入力値を書き換えることはありません。

## 会計規約

会計恒等式は、表の意味が明示されている場合だけ評価します。

引数なしの `AccountingConvention()` は意図的に保守的です。

```python
from ioaudit import AccountingConvention

accounting = AccountingConvention()
```

会計上の意味を持つフィールドは原則として `"unknown"` になり、該当する会計診断は推測せず `SKIPPED` になります。

一般的な会計構造には、明示的なpresetを利用できます。

```python
accounting = AccountingConvention.domestic_competitive(
    inflow_sign="negative",
    trade_representation="outflows_in_Y",
)
```

そのほか、

```python
AccountingConvention.domestic_noncompetitive()
AccountingConvention.total_transactions()
```

があります。これらは国名ではなく、会計構造を表すpresetです。

すべて明示することもできます。

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

`Y`、`V` とともに `IOSystem` に渡します。

```python
Y = np.array([[6.0], [7.0]])
V = np.array([[5.0, 8.0]])

io = IOSystem(
    Z=Z,
    x=x,
    sectors=["農業", "製造業"],
    Y=Y,
    V=V,
    accounting=accounting,
)

report = audit(io)
```

`ioaudit` は、輸入ベクトルが存在するという理由だけで、輸入処理や会計式を推測しません。

## 丸め誤差

公表された産業連関表では、表示単位による丸め残差が生じることがあります。

許容値を明示すると、完全一致と丸め範囲内の残差を区別できます。

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

許容範囲内の非ゼロ残差は `ROUNDING_LEVEL` として記録されます。指定した tolerance は provenance に保存され、入力値そのものは変更されません。

## 移輸入・移輸出

地域表・全国表の外部フローは `TradeFlows` で明示できます。

```python
from ioaudit import TradeFlows

trade = TradeFlows(
    interregional_inflows=interregional_inflows,
    international_imports=imports,
    interregional_outflows=interregional_outflows,
    international_exports=exports,
)
```

合算済みのフローしかない場合は、`combined_inflows` / `combined_outflows` を利用できます。

```python
trade = TradeFlows(
    combined_inflows=inflows,
    combined_outflows=outflows,
)
```

`AccountingConvention` では、交易が最終需要に埋め込まれているのか、`Y` に移輸出として含まれているのか、別掲なのか、不明なのかを宣言します。

`ioaudit` はこの関係を自動推定しません。同じ側で合算表現と分割表現が同時に与えられた場合も、二重計上せず矛盾として報告します。

交易ベクトルは供給・需要側のフローとして扱い、購入部門別の外部投入データがない限り、列側の投入会計へ流用しません。

## 外部参照との比較

既存の技術係数行列やLeontief逆行列がある場合、`A_reference` / `L_reference` として指定できます。

```python
io = IOSystem(
    Z=Z,
    x=x,
    sectors=sectors,
    A_reference=A_ref,
    L_reference=L_ref,
)
```

内部で再計算した行列と、shape、labels、数値差などを比較できます。

## Metadata と provenance

表の意味を後から確認できるよう、metadataを保持できます。

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

主に次の項目を確認します。

- `year`
- `unit`
- `price_basis`
- `currency`
- `valuation`

各監査には `report.provenance` が付き、主に次を記録します。

- ioaudit version
- input SHA-256 hash
- requested numerical method
- selected numerical method
- accounting tolerance
- scale diagnostic settings
- applied thresholds
- audit timestamp

## CSVなどの事前診断

`IOSystem` を構築する前の区切りテキストは `inspect_csv()` / `inspect_delimited()` で確認できます。

```python
from ioaudit import inspect_csv

raw_report = inspect_csv(
    "io.csv",
    delimiter=",",
    encoding="cp932",
)

print(raw_report.summary())
```

主な診断対象は、

- encoding / BOM
- delimiter
- 空行
- 列数不一致
- 空・重複ヘッダー
- trailing delimiter
- 引用符異常
- 不要な空白
- 数値として読めないトークン
- NaN / Inf 風トークン
- 未引用の桁区切りらしきパターン
- 注記行
- 途中で再出現した見出し

です。

ただし、ファイルのどこが `Z`、`x`、`Y`、`V` なのかを自動推定したり、脚注・合計行を自動削除したりはしません。

```text
file diagnostics
    ↓
parsing by the caller
    ↓
IOSystem
    ↓
audit()
```

## 結果の利用

```python
report.summary()
report.to_dict()
report.to_json()
report.to_dataframe()
report.passed()
```

CIや自動処理では、監査結果をgateとして利用できます。

```python
report.raise_for_status()
```

会計相対残差を明示的な条件にする場合は、例えば次のように指定します。

```python
report.raise_for_status(
    max_relative_residual=1e-4,
)
```

## 数値計算ルート

```python
report = audit(io, numerical_method="auto")
```

`"auto"` は入力サイズや疎行列かどうかに応じて dense / iterative route を選択します。選択した方法や推定情報は `report.methods` と provenance に記録されます。

## 対象範囲

v0.1 は、**単一の対称産業連関表（symmetric input-output table）に対する分析前診断**に限定しています。

供給・使用表（Supply and Use Tables; SUT）は、v0.1では直接の監査対象ではありません。SUTから対称産業連関表へ変換済みのデータは監査できますが、SUTからIOTへの変換自体は `ioaudit` の対象外です。

また、次の機能は提供しません。

- RAS / GRAS / KRAS
- 行列バランシング
- 表の自動修正
- regionalization
- trade estimation
- data download
- Excelの自動解釈
- sector auto-matching
- table comparison
- hierarchy / aggregation diagnostics
- impact analysis
- multiplier analysis
- structural decomposition analysis
- policy ranking
- visualization
- GUI

`ioaudit` は産業連関分析そのものを行うライブラリではありません。

**「この表を分析コードに渡してよいか」を診断するためのライブラリです。**

## Installation

現在の開発版は、リポジトリをcloneしたうえで次のようにインストールできます。

```bash
pip install -e .
```

Python 3.10以上が必要です。

テスト用依存関係を含める場合は、

```bash
pip install -e ".[test]"
```

を利用できます。

## Tests

```bash
pytest
```

## License

MIT License.

---

# English

`ioaudit` is a Python library for checking input-output tables **before** they are passed to analytical code.

It audits data structure, accounting consistency, matrix orientation, zero-output sectors, possible subtotal double counting, powers-of-ten scale errors, and numerical stability in Leontief systems.

> **Diagnose, do not repair.**

`ioaudit` reports problems and ambiguity, but it does not silently transpose, rebalance, delete, rescale, or otherwise repair the supplied table. When required information is unavailable, the affected diagnostic is reported as `SKIPPED` rather than inferred.

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
report.reference
report.signs
report.scale
report.components
report.metadata
report.provenance
```

## Diagnostic statuses

`ioaudit` does not reduce every diagnostic to a simple boolean.

- `PASS`: no problem was identified under the declared conditions
- `FAIL`: an explicit inconsistency or configured threshold violation was identified
- `WARNING`: evidence or a candidate issue requires review
- `SKIPPED`: the available information is insufficient for a safe determination
- `ROUNDING_LEVEL`: a non-zero residual is within an explicitly declared rounding tolerance

`SKIPPED` does not mean that the data passed. It means that `ioaudit` declined to infer missing semantics.

## What does ioaudit check?

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

When `Y`, `V`, and an explicit accounting convention are available, `ioaudit` can evaluate input- and output-side accounting residuals, including:

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

`ioaudit` safely constructs the technical coefficient matrix

```text
A = Z diag(x)^(-1)
```

and checks:

- coefficient finiteness
- coefficient sums
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

## Accounting conventions

Accounting identities are evaluated only under an explicitly declared interpretation of the table.

The plain constructor is intentionally conservative:

```python
from ioaudit import AccountingConvention

accounting = AccountingConvention()
```

Its semantic fields default to `"unknown"`. Affected accounting checks are therefore `SKIPPED` rather than evaluated under an implicit national or statistical-office convention.

Explicit presets are available for common accounting structures:

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

A convention can also be declared fully explicitly:

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

Then pass it to `IOSystem` together with `Y` and `V`:

```python
Y = np.array([[6.0], [7.0]])
V = np.array([[5.0, 8.0]])

io = IOSystem(
    Z=Z,
    x=x,
    sectors=["agriculture", "manufacturing"],
    Y=Y,
    V=V,
    accounting=accounting,
)

report = audit(io)
```

`ioaudit` does not infer import treatment or an accounting equation merely from the presence of an import vector.

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

Trade vectors are treated as supply/demand-side flows and are not reused as user-specific intermediate inputs unless such information is explicitly available.

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

`ioaudit` compares internally calculated matrices with the supplied references and reports structural and numerical differences.

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

File-level diagnostics can report issues such as:

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

## Using the report

```python
report.summary()
report.to_dict()
report.to_json()
report.to_dataframe()
report.passed()
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

## Numerical routes

```python
report = audit(io, numerical_method="auto")
```

With `"auto"`, `ioaudit` selects a dense or iterative numerical route according to the input size and whether the matrix is sparse. The selected route and approximation metadata are recorded in `report.methods` and provenance.

## Scope

Version 0.1 focuses on **preflight diagnostics for a single symmetric input-output table (SIOT)**.

Supply and Use Tables (SUTs) are not directly supported in v0.1. A symmetric input-output table derived from a SUT can be audited, but SUT-to-IOT transformation itself is outside the scope of `ioaudit`.

The package also does not provide:

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

## Tests

```bash
pytest
```

## License

MIT License.
