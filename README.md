# ioaudit

`ioaudit` は、産業連関表を分析へ投入する前に、データ構造、行列の向き、会計整合性、投入係数、Leontief 系の数値安定性、外部参照行列との差を機械的に診断する Python ライブラリです。

## Installation

```bash
pip install -e .
```

Python 3.10 以上が必要です。

## Quickstart

```python
import numpy as np

from ioaudit import IOSystem, TradeFlows, AccountingConvention, audit

Z = np.array([[10.0, 2.0], [3.0, 8.0]])
x = np.array([18.0, 18.0])
sectors = ["agriculture", "manufacturing"]
Y = np.array([[7.0], [7.0]])
V = np.array([[5.0, 8.0]])
imports = np.array([-1.0, 0.0])
trade = TradeFlows(international_imports=imports)

io = IOSystem(
    Z=Z,
    x=x,
    sectors=sectors,
    Y=Y,
    V=V,
    trade=trade,
    accounting=AccountingConvention(
        transaction_scope="domestic",
        import_treatment="competitive",
        trade_representation="outflows_in_Y",
        external_flow_scope="international",
        inflow_sign="negative",
        outflow_sign="positive",
    ),
)
report = audit(io)
print(report.summary())
print(report.accounting.max_relative_residual)
print(report.stability.spectral_radius)
print(report.orientation.possible_transpose)
```

丸め誤差を考慮する場合は、許容値を明示して監査します。指定値はレポートと provenance に保存され、入力値は変更されません。

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

`raise_for_status()` は、Accountingの明示的なtoleranceと矛盾しないよう、会計相対残差ゲートを既定では追加しません。相対残差をCI条件にする場合は `report.raise_for_status(max_relative_residual=1e-4)` のように明示してください。`max_spectral_radius` の既定値は `1.0` です。

## Design principle

**diagnose, do not repair**

ioaudit は入力データを自動修正しません。整合的なゼロ産出部門は、元の `IOSystem` を変更せず、計算上の係数列を安全にゼロとして扱います。ゼロ産出なのに取引列が非ゼロの部門は係数・Leontief計算を `SKIPPED` にして、見かけ上の解を作りません。輸入の扱いは `AccountingConvention` で宣言し、輸入ベクトルの存在だけから会計式を推測しません。

`domestic/competitive` では、`inflow_sign` を指定します。`negative` は `imports=-M` として `x = row_sum(Z) + f + imports`、`positive` は `imports=M` として `x = row_sum(Z) + f - imports` を適用します。`unknown` の場合は符号を推測せず、調整済みの産出側会計監査を `SKIPPED` にします。`inflow_sign` を省略した場合の互換デフォルトは `negative` です。`domestic/noncompetitive` では、明示した交易フローと `inflow_sign` / `outflow_sign` の宣言に基づいて会計式を構成します。必要な情報がない場合は該当する診断を `SKIPPED` にします。

### Competitive import sign convention

v0.1 の `domestic/competitive` では、`inflow_sign="negative" | "positive" | "unknown"` を使用します。日本の産業連関表で一般的な負値の輸入行には `inflow_sign="negative"`、正の輸入額 `M` には `inflow_sign="positive"` を指定してください。`unknown` では符号を推測・変換しません。旧APIの `import_sign` は `inflow_sign` の互換エイリアスです。`import_treatment="none"` または `transaction_scope="total"` では `import_sign` / `inflow_sign` は会計計算に適用せず、レポートに `import_sign not applicable` を残します。`trade_representation="unknown"` はこの指定より優先され、Yとの関係が不明なため産出側会計を `SKIPPED` にします。

## TradeFlows

地域表・全国表の交易は、`imports` / `exports` の個別引数ではなく `TradeFlows` にまとめて指定します。

```python
trade = TradeFlows(
    interregional_inflows=imin,
    international_imports=imports,
    interregional_outflows=imout,
    international_exports=exports,
)
```

合算表では `combined_inflows` / `combined_outflows` を使用します。片側で合算表と分割表を同時に指定すると、二重計上防止のため該当する会計診断を `SKIPPED` にします。`external_flow_scope` は `international`、`interregional`、`both` のいずれかを宣言します。`trade_representation` は `embedded`、`outflows_in_Y`、`separate`、`unknown` から選び、`unknown` ではYとの関係を推測しません。

交易ベクトルは供給・需要側のフローとして扱い、購入部門別の輸移入投入を列側の投入会計へ流用しません。`external_inputs_by_user` のような購入部門別データがない場合、trade-adjusted input balance は `SKIPPED` です。

## Component and structure diagnostics

`report.components` は、`Y` の合計列や `V` の付加価値計行が他の構成要素の合計に近い場合に、二重計上候補として報告します。候補を自動的に除外せず、会計監査の `sum(axis=...)` も変更しません。

subtotal候補が検出された場合は、曖昧な列・行を勝手に選ばないため、Y側のoutput balanceまたはV側のinput balanceを `SKIPPED` にします。なお、2成分しかないY/Vでは、ラベルのない数値一致だけではsubtotalと判定しません。

`report.structure` には、`possible_nonsector_rows` / `possible_nonsector_columns`、完全一致する `possible_duplicate_rows` / `possible_duplicate_columns`、Unicode幅・空白を正規化したラベル一致、`duplicate_labels_after_normalization` が含まれます。`合計`、`輸入`、`最終需要`、`付加価値` などのラベルはZに混入した可能性として警告されます。

`report.zero_output` は、`all_zero_rows`、`all_zero_columns`、`isolated_sectors` を返します。これらは切り出しや欠損の確認材料であり、自動削除やゼロ置換は行いません。

## Metadata and provenance

表の意味を再現できるよう、`metadata` の `year`、`unit`、`price_basis` を必須推奨項目として監査します。`currency` と `valuation` も推奨項目です。値を推測せず、欠落は `report.metadata` に残します。

各監査には、入力内容のSHA-256 `input_hash`、ioauditバージョン、指定・選択した数値計算方式、会計tolerance、scale候補条件、実行時刻、適用した閾値を含む `report.provenance` が付きます。

## File diagnostics

IOSystem に渡す前の区切りテキストは、`inspect_csv()` で読み取り上の異常を確認できます。

```python
from ioaudit import inspect_csv

raw_report = inspect_csv("io.csv", delimiter=",", encoding="cp932")
print(raw_report.summary())
```

この前段は encoding/BOM、delimiter、空行、列数不一致、重複・空ヘッダー、trailing delimiter、引用符異常、空白、数値として読めないトークン、NaN/Inf風トークン、桁区切りの未引用らしきパターン、注記行や途中見出しの再出現を報告します。桁区切りの変換、行列範囲の推測、脚注や合計行の削除、Z・x・Y・Vの自動抽出は行いません。

```text
file diagnostics -> parsing by the caller -> IOSystem -> audit()
```

## What ioaudit does not do

v0.1 は単一 IO 表の監査に限定しています。RAS、GRAS、KRAS、行列バランシング、表修正、地域化、貿易推計、データダウンロード、Excel 自動解析、セクター自動マッチング、品質スコア、真偽判定、表比較、階層・集計診断、政策ランキング、調査優先順位付け、可視化、GUI は実装しません。

## Numerical routes

`audit(io, numerical_method="auto")` は小規模行列では dense route、大規模行列では iterative route を選択します。`dense` は NumPy の通常計算、`iterative` は SciPy の疎行列固有値計算・疎 LU・条件数推定を使用します。選択結果と推定の有無は `report.methods` に保存されます。

## Scale diagnostics

`report.scale` は、宣言された会計残差を使って桁倍率の候補を診断します。`10**k`（`k=-6..6`、1を除く）を「現在値に掛ける係数」として仮想的に適用し、`x`・`Z`・`Y`・`V`の全体倍率、`Z`の行・列倍率、さらに行側と列側の両方を改善するセル倍率を候補として記録します。`A_reference` がある場合はセル候補に参照係数との差の改善も記録します。候補は修正値ではなく、残差改善の証拠です。

行・列候補は反対側の会計残差も評価します。反対側を監査できない候補は `opposite_balance_available=False`、`evidence_level="one_sided"` として保存されます。反対側の残差を10%超悪化させる候補は報告しません。

```python
for candidate in report.scale.possible_cell_scale_errors:
    print(candidate["row"], candidate["column"], candidate["candidate_factor"])
```

会計残差が利用できない場合は `report.scale.status == "SKIPPED"` になります。桁ミスの自動修正や、候補の自動採用は行いません。

## Tests

```bash
pytest
```
