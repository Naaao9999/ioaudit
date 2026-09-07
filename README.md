# ioaudit

**Preflight diagnostics for input-output tables.**

`ioaudit` は、産業連関表を分析へ投入する前に、データ構造、行列の向き、会計整合性、投入係数、Leontief 系の数値安定性、外部参照行列との差を機械的に診断する Python ライブラリです。

`ioaudit` mechanically audits an input-output table before it is used in analysis. It checks data structure, matrix orientation, accounting identities, technical coefficients, Leontief-system stability, and differences from reference matrices.

## Purpose / 目的

ioaudit の目的は、入力表にありがちな silent error を分析前に見つけることです。入力値や行列を自動修正せず、診断結果と根拠を返します。

The goal is to find common silent errors before analysis. The library returns diagnostics and evidence; it does not silently modify the input table or infer missing accounting conventions.

## Installation / インストール

```bash
pip install -e .
```

Python 3.10 以上が必要です。

Python 3.10 or later is required.

## Quickstart / 基本利用

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

最低限、取引行列 `Z`、産出額 `x`、部門名 `sectors` があれば監査できます。Y/Vや `AccountingConvention` を指定すると、会計監査が追加されます。

At minimum, an audit can be run with the transaction matrix `Z`, output vector `x`, and sector identifiers. Adding `Y`, `V`, and an explicit `AccountingConvention` enables accounting diagnostics.

個別の診断結果には、例えば次のようにアクセスできます。

```python
print(report.structure.status)
print(report.orientation.possible_transpose)
print(report.stability.spectral_radius)
print(report.scale.possible_cell_scale_errors)
```

The public entry points are `IOSystem`, `TradeFlows`, `AccountingConvention`, and `audit`. Reports also provide `summary()`, `to_dict()`, `to_json()`, and `to_dataframe()`.

会計情報が不足している診断は、値を推測せず `SKIPPED` になります。

Diagnostics that require unavailable accounting information are marked `SKIPPED` rather than inferred.

## Design principle / 設計原則

**diagnose, do not repair**

ioaudit は入力データを自動修正しません。整合的なゼロ産出部門は、元の `IOSystem` を変更せず、計算上の係数列を安全にゼロとして扱います。ゼロ産出なのに取引列が非ゼロの部門は係数・Leontief計算を `SKIPPED` にして、見かけ上の解を作りません。

ioaudit never repairs input data. A consistent zero-output sector is handled as a zero coefficient column during calculations without changing the original `IOSystem`. If a zero-output sector has nonzero transactions, coefficient and Leontief calculations are marked `SKIPPED` rather than producing a misleading result.

輸入の扱いは `AccountingConvention` で宣言し、輸入ベクトルの存在だけから会計式を推測しません。

Import treatment is declared through `AccountingConvention`; the presence of an import vector alone is never used to infer an accounting equation.

### Competitive import sign convention / 競争輸入の符号規約

v0.1 の `domestic/competitive` では、`inflow_sign="negative" | "positive" | "unknown"` を使用します。日本の産業連関表で一般的な負値の輸入行には `inflow_sign="negative"`、正の輸入額 `M` には `inflow_sign="positive"` を指定してください。

For `domestic/competitive` in v0.1, use `inflow_sign="negative" | "positive" | "unknown"`. Use `inflow_sign="negative"` for signed negative import rows commonly found in Japanese IO tables, and `inflow_sign="positive"` when imports are stored as positive magnitudes `M`.

`negative` は `imports=-M` として `x = row_sum(Z) + f + imports`、`positive` は `imports=M` として `x = row_sum(Z) + f - imports` を適用します。`unknown` では符号を推測せず、調整済みの産出側会計監査を `SKIPPED` にします。旧APIの `import_sign` は `inflow_sign` の互換エイリアスです。

`negative` applies `x = row_sum(Z) + f + imports` for `imports=-M`; `positive` applies `x = row_sum(Z) + f - imports` for `imports=M`. With `unknown`, no sign inference is performed and the adjusted output balance is `SKIPPED`. The legacy `import_sign` argument is accepted as a compatibility alias for `inflow_sign`.

`import_treatment="none"` または `transaction_scope="total"` では import sign は会計計算に適用されず、レポートに `import_sign not applicable` が残ります。`trade_representation="unknown"` はこの指定より優先され、Yとの関係が不明なため産出側会計を `SKIPPED` にします。

With `import_treatment="none"` or `transaction_scope="total"`, the import sign is not applied and the report records `import_sign not applicable`. `trade_representation="unknown"` takes precedence and skips output accounting because the relationship between `Y` and trade is unknown.

## TradeFlows / 交易フロー

地域表・全国表の交易は、`imports` / `exports` の個別引数ではなく `TradeFlows` にまとめて指定します。

For national and regional tables, provide trade through `TradeFlows` instead of separate legacy `imports` / `exports` arguments.

```python
trade = TradeFlows(
    interregional_inflows=imin,
    international_imports=imports,
    interregional_outflows=imout,
    international_exports=exports,
)
```

合算表では `combined_inflows` / `combined_outflows` を使用します。片側で合算表と分割表を同時に指定すると、二重計上防止のため該当する会計診断を `SKIPPED` にします。

Use `combined_inflows` / `combined_outflows` for combined tables. Supplying combined and split representations on the same side causes the affected accounting diagnostic to be `SKIPPED` to prevent double counting.

`external_flow_scope` は `international`、`interregional`、`both` のいずれかを宣言します。`trade_representation` は `embedded`、`outflows_in_Y`、`separate`、`unknown` から選び、`unknown` ではYとの関係を推測しません。

Declare `external_flow_scope` as `international`, `interregional`, or `both`. Choose `trade_representation` from `embedded`, `outflows_in_Y`, `separate`, and `unknown`; `unknown` never triggers an inference about what is included in `Y`.

交易ベクトルは供給・需要側のフローとして扱い、購入部門別の輸移入投入を列側の投入会計へ流用しません。購入部門別の外部投入データがない場合、trade-adjusted input balance は `SKIPPED` です。

Trade vectors are treated as supply/demand-side flows and are not reused as user-specific intermediate inputs. Without user-specific external-input data, the trade-adjusted input balance is `SKIPPED`.

## Component and structure diagnostics / 構成要素・構造診断

`report.components` は、`Y` の合計列や `V` の付加価値計行が他の構成要素の合計に近い場合に、二重計上候補として報告します。候補を自動的に除外せず、会計監査の `sum(axis=...)` も変更しません。

`report.components` reports possible double counting when a total column in `Y` or a value-added total row in `V` is close to the sum of its components. Candidates are reported, not removed, and the accounting sums are not changed automatically.

subtotal候補が検出された場合は、曖昧な列・行を選ばないため、Y側のoutput balanceまたはV側のinput balanceを `SKIPPED` にします。2成分しかないY/Vでは、ラベルのない数値一致だけではsubtotalと判定しません。

When a subtotal candidate is detected, the corresponding output or input balance is `SKIPPED` because the correct subset is ambiguous. For a two-component `Y` or `V`, an unlabeled numeric match alone is not treated as a subtotal.

`report.structure` には、`possible_nonsector_rows` / `possible_nonsector_columns`、完全一致する `possible_duplicate_rows` / `possible_duplicate_columns`、Unicode幅・空白を正規化したラベル一致、`duplicate_labels_after_normalization` が含まれます。`合計`、`輸入`、`最終需要`、`付加価値` などのラベルはZへの混入候補として警告されます。

`report.structure` includes possible non-sector rows and columns, exact duplicate rows and columns, normalized label matches, and `duplicate_labels_after_normalization`. Labels such as `合計`, `輸入`, `最終需要`, and `付加価値` are reported as possible non-sector content in `Z`.

`report.zero_output` は、`all_zero_rows`、`all_zero_columns`、`isolated_sectors` を返します。これらは切り出しや欠損の確認材料であり、自動削除やゼロ置換は行いません。

`report.zero_output` returns `all_zero_rows`, `all_zero_columns`, and `isolated_sectors`. These are evidence for checking extraction and missing values; no rows are deleted and no values are replaced with zero.

## Accounting tolerance / 会計許容差

丸め誤差を考慮する場合は、許容値を明示して監査します。指定値はレポートと provenance に保存され、入力値は変更されません。

Declare tolerances when published tables are rounded. The selected values are stored in the report and provenance, and the input values remain unchanged.

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

会計診断は、完全一致なら `PASS`、許容範囲内の丸め差なら `ROUNDING_LEVEL`、許容範囲外なら `FAIL` を返します。`raise_for_status()` は既定では会計相対残差ゲートを追加しません。相対残差をCI条件にする場合は `report.raise_for_status(max_relative_residual=1e-4)` のように明示してください。`max_spectral_radius` の既定値は `1.0` です。

Accounting diagnostics return `PASS` for exact agreement, `ROUNDING_LEVEL` for residuals within the declared tolerance, and `FAIL` otherwise. `raise_for_status()` does not add an accounting relative-residual gate by default. Add one explicitly for CI, for example `report.raise_for_status(max_relative_residual=1e-4)`. The default `max_spectral_radius` is `1.0`.

## Metadata and provenance / メタデータ・来歴

表の意味を再現できるよう、`metadata` の `year`、`unit`、`price_basis` を必須推奨項目として監査します。`currency` と `valuation` も推奨項目です。値を推測せず、欠落は `report.metadata` に残します。

To make the table auditable and reproducible, `year`, `unit`, and `price_basis` are recommended metadata fields. `currency` and `valuation` are also recommended. Missing metadata is reported rather than inferred.

各監査には、入力内容のSHA-256 `input_hash`、ioauditバージョン、指定・選択した数値計算方式、会計tolerance、scale候補条件、実行時刻、適用した閾値を含む `report.provenance` が付きます。

Each audit includes `report.provenance` with an SHA-256 `input_hash`, the ioaudit version, requested and selected numerical methods, accounting tolerance, scale-candidate settings, execution time, and applied thresholds.

## File diagnostics / ファイル入力診断

IOSystem に渡す前の区切りテキストは、`inspect_csv()` で読み取り上の異常を確認できます。

Delimited text can be inspected before constructing an `IOSystem` with `inspect_csv()`.

```python
from ioaudit import inspect_csv

raw_report = inspect_csv("io.csv", delimiter=",", encoding="cp932")
print(raw_report.summary())
```

この前段は encoding/BOM、delimiter、空行、列数不一致、重複・空ヘッダー、trailing delimiter、引用符異常、空白、数値として読めないトークン、NaN/Inf風トークン、桁区切りの未引用らしきパターン、注記行や途中見出しの再出現を報告します。

The file-level diagnostic reports encoding/BOM, delimiter, blank rows, inconsistent column counts, duplicate or empty headers, trailing delimiters, quoting anomalies, whitespace, non-numeric tokens, NaN/Inf-like tokens, possible unquoted thousands separators, note rows, and repeated headers.

桁区切りの変換、行列範囲の推測、脚注や合計行の削除、Z・x・Y・Vの自動抽出は行いません。

It does not convert thousands separators, infer matrix ranges, delete notes or totals, or automatically extract `Z`, `x`, `Y`, and `V`.

```text
file diagnostics -> parsing by the caller -> IOSystem -> audit()
```

## Numerical routes / 数値計算方式

`audit(io, numerical_method="auto")` は小規模行列では dense route、大規模行列では iterative route を選択します。`dense` は NumPy の通常計算、`iterative` は SciPy の疎行列固有値計算・疎LU・条件数推定を使用します。選択結果と推定の有無は `report.methods` に保存されます。

`audit(io, numerical_method="auto")` selects a dense route for small matrices and an iterative route for large matrices. `dense` uses standard NumPy calculations; `iterative` uses SciPy sparse eigenvalue, sparse-LU, and condition-estimation routines. The selected route and whether values are estimated are stored in `report.methods`.

## Scale diagnostics / 桁・単位診断

`report.scale` は、宣言された会計残差を使って桁倍率の候補を診断します。`10**k`（`k=-6..6`、1を除く）を現在値に掛ける係数として仮想的に適用し、`x`・`Z`・`Y`・`V`の全体倍率、`Z`の行・列倍率、さらに行側と列側の両方を改善するセル倍率を候補として記録します。`A_reference` がある場合はセル候補に参照係数との差の改善も記録します。

`report.scale` diagnoses candidate scale factors using declared accounting residuals. It virtually applies `10**k` for `k=-6..6` except `1` to global `x`, `Z`, `Y`, and `V`, to `Z` rows and columns, and to individual cells that improve both sides. When `A_reference` is available, reference-coefficient improvement is also recorded.

候補は修正値ではなく残差改善の証拠です。行・列候補は反対側の会計残差も評価し、反対側を10%超悪化させる候補は報告しません。反対側を監査できない候補は `opposite_balance_available=False`、`evidence_level="one_sided"` として保存されます。

Candidates are evidence of residual improvement, not repairs. Row and column candidates are checked against the opposite accounting side; candidates that degrade it by more than 10% are omitted. If the opposite side is unavailable, the candidate is marked with `opposite_balance_available=False` and `evidence_level="one_sided"`.

```python
for candidate in report.scale.possible_cell_scale_errors:
    print(candidate["row"], candidate["column"], candidate["candidate_factor"])
```

会計残差が利用できない場合は `report.scale.status == "SKIPPED"` になります。桁ミスの自動修正や候補の自動採用は行いません。

When accounting residuals are unavailable, `report.scale.status == "SKIPPED"`. Scale errors are never repaired or automatically accepted.

## What ioaudit does not do / 対象外

v0.1 は単一 IO 表の監査に限定しています。RAS、GRAS、KRAS、行列バランシング、表修正、地域化、貿易推計、データダウンロード、Excel 自動解析、セクター自動マッチング、品質スコア、真偽判定、表比較、階層・集計診断、政策ランキング、調査優先順位付け、可視化、GUI は実装しません。

v0.1 is limited to auditing a single IO table. It does not implement RAS, GRAS, KRAS, matrix balancing, table correction, regionalization, trade estimation, data downloading, automatic Excel parsing, automatic sector matching, quality scores, truth judgments, table comparison, hierarchical or aggregation diagnostics, policy ranking, survey prioritization, visualization, or a GUI.

## Tests / テスト

```bash
pytest
```

ローカルテストは小さなsynthetic IO表を使用し、外部データをダウンロードしません。GitHub Actionsでは、pushとpull requestごとにPython 3.10〜3.13で同じpytestを実行します。e-Statの実データ検証は、アプリケーションIDを明示的に設定した環境で個別に実行してください。

The test suite uses small synthetic IO tables and does not download external data. Live e-Stat checks should be run separately with an explicitly configured application ID.

GitHub Actions runs the same pytest suite on Python 3.10 through 3.13 for every push and pull request.
