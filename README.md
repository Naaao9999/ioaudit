# ioaudit

**産業連関表を分析する前に、表そのものを監査する Python ライブラリ。**  
**Preflight diagnostics for input-output tables.**

[日本語](#日本語) | [English](#english)

---

# 日本語

`ioaudit` は、産業連関表を分析に使う前に、データや会計関係に問題がないかを `audit()` でまとめて確認します。

> **Diagnose, do not repair. — 診断するが、自動修正しない。**

問題が見つかっても、`ioaudit` は表を勝手に転置・補正・削除・再スケールしません。診断に必要な情報が不足している場合も、値や会計規約を推測せず `SKIPPED` として扱います。

## できること

- `Z`、`x`、`Y`、`V` の形状、数値型、部門ラベル、並び順を確認
- `Z` の行・列の向きを取り違えていないかを確認
- 合計行・列、非部門項目、重複ラベル、ゼロ行・ゼロ列を検出
- 指定した会計規約に基づいて、投入側・産出側の会計残差を計算
- `Y` / `V` に小計が混ざって二重計上になっていないかを確認
- 交易フローや `input_adjustments` を安全に会計計算へ使えるかを確認
- 技術係数行列 `A`、スペクトル半径、`I - A` の可逆性、条件数、Leontief逆行列を確認
- `A_reference` / `L_reference` がある場合は、再計算した行列との差を確認
- 会計残差から、10倍・100倍・1000倍などの桁違い候補を検出
- 結果を要約、JSON、DataFrameとして出力し、CIの判定にも利用

CSV等のファイル形式は `inspect_csv()` で別途確認できます。ファイルから表の範囲や部門を自動推定する機能は含みません。

## クイックスタート

実データを `IOSystem` に渡すまでの責務分担と、会計規約を選ぶ3つの完全例は [integration guide](docs/integration-guide.md) にまとめています。

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
report.structure       # Z/x/Y/V とラベルの構造
report.orientation     # 行列の向き・転置候補
report.accounting      # 投入側・産出側の会計残差
report.zero_structure  # ゼロ産出・ゼロ行列構造
report.coefficients    # 技術係数 A
report.stability       # I-A、スペクトラル半径、条件数
report.reference       # A/L参照行列との差
report.signs           # 負値の位置と値
report.scale           # 桁・単位ミスの候補
report.components      # Y/V subtotal二重計上候補
report.metadata        # 年・単位等の意味情報
report.provenance      # 入力hash・実行条件
```

## 診断ステータス

`ioaudit` は、すべての診断結果を単純な真偽値だけで表すわけではありません。

- `PASS`: 指定された条件の範囲で問題が確認されなかった
- `FAIL`: 明示的な不整合または設定した閾値違反が確認された
- `WARNING`: 確認すべき候補や証拠がある
- `SKIPPED`: 必要な情報が不足しており、安全に判定できない
- `AVAILABLE`: 計算はできたが、合否を決める基準が指定されていない

会計残差が明示した丸め許容範囲内にある場合は、`status="PASS"` と `residual_class="rounding_level"` の組み合わせで表します。

`SKIPPED` は「問題なし」を意味しません。必要な意味情報を `ioaudit` が推測しなかったことを意味します。

## 何を診断するか

### 構造

- `Z` が2次元の正方行列か
- `x` と部門数が整合しているか
- NaN / Inf / 非数値が含まれていないか
- 行・列・部門ラベルが整合しているか
- `Y`、`V`、`TradeFlows`、`input_adjustments` の部門軸が整合しているか
- 重複ラベルがないか
- Unicode幅や空白を正規化した後に重複が生じないか
- 合計行・合計列や非部門項目らしきラベルが `Z` に混入していないか
- 完全に同一の行・列がないか

### 行列の向き

- 行ラベルと列ラベルの対応
- 部門順序
- `x` の対応関係
- 現在の向きと転置した場合の会計残差の比較
- `possible_transpose`

転置の可能性を報告しても、行列を自動的に転置することはありません。

### 会計整合性

`Y`、`V` と明示的な会計規約が利用できる場合、投入側・産出側の会計残差を診断します。

- 部門別残差
- 絶対残差
- 相対残差
- MAE
- RMSE
- 最大残差
- 残差分類

引数なしの `AccountingConvention()` は、会計上の意味を推測しない保守的な設定です。意味情報が `"unknown"` のままなら、影響する会計診断は `SKIPPED` になります。

### ゼロ産出・ゼロ構造

`report.zero_structure` は次を診断します。

- ゼロ産出部門
- 全ゼロ行
- 全ゼロ列
- 孤立部門
- ゼロ産出と取引構造の不整合
- 全ゼロ行に正の最終需要がある証拠
- 全ゼロ列に正の付加価値がある証拠

これらは表の切り出しや欠損を確認するための診断情報であり、行・列の自動削除やゼロ置換は行いません。

### 投入係数・Leontief 系

技術係数行列

```text
A = Z diag(x)^(-1)
```

を安全に構成し、次を診断します。

- 係数が有限か
- 係数和
- スペクトル半径
- `I - A` の可逆性
- 条件数
- Leontief 逆行列が有限か

### 合計列・合計行の二重計上候補

`report.components` は、`Y` の最終需要計や `V` の付加価値計など、他の構成要素をすでに含んでいる可能性がある列・行を診断します。

```python
report.components.possible_subtotal_columns
report.components.possible_subtotal_rows
report.components.double_count_risk
```

候補を自動的に除外することはありません。小計候補が検出され、正しい構成要素の選択が曖昧な場合は、対応する `output_balance` または `input_balance` を `SKIPPED` にします。

成分数が12以下の場合は小規模な部分集合も探索し、部分小計の候補に対して `subset_indices`、`subset_labels`、`subset_size`、`sum_similarity` を返します。2成分しかない `Y` / `V` では、ラベルのない数値一致だけでは小計と判定しません。

### 桁・単位ミスの候補

`report.scale` は、利用可能な会計残差を使って、10のべき乗による桁違いの候補を探索します。

対象は次のとおりです。

- `x` 全体
- `Z` 全体
- `Y` 全体
- `V` 全体
- `Z` の行
- `Z` の列
- `Z` のセル

```python
for candidate in report.scale.possible_cell_scale_errors:
    print(
        candidate["row"],
        candidate["column"],
        candidate["candidate_factor"],
    )
```

ここで報告される候補は修正値ではなく、残差がどの程度改善するかにもとづく診断上の証拠です。`ioaudit` が入力値を書き換えることはありません。

## 会計規約

会計恒等式は、表の意味が明示されている場合だけ評価します。

引数なしの `AccountingConvention()` は意図的に保守的です。

```python
from ioaudit import AccountingConvention

accounting = AccountingConvention()
```

`transaction_scope`、`import_treatment`、`trade_representation`、`external_flow_scope`、`inflow_sign`、`outflow_sign`、`input_representation` は既定で `"unknown"` です。該当する会計診断は推測せず `SKIPPED` になります。

一般的な会計構造にはプリセットを利用できます。

```python
accounting = AccountingConvention.domestic_competitive(
    inflow_sign="negative",
    trade_representation="outflows_in_Y",
    external_flow_scope="international",
    outflow_sign="positive",
    input_representation="complete",
)
```

そのほか、次のプリセットがあります。

```python
AccountingConvention.domestic_noncompetitive()
AccountingConvention.total_transactions()
```

`domestic_competitive()` と `domestic_noncompetitive()` は、それぞれ名称から確定する `transaction_scope` と `import_treatment` だけを固定します。交易の格納方法、符号、投入側の完全性は既定では `"unknown"` のままです。

`total_transactions()` は `transaction_scope="total"` と `import_treatment="none"` を固定しますが、付加価値ブロックが投入側を完全に説明するかどうかは推測せず、`input_representation="unknown"` とします。

会計規約をすべて明示することもできます。

```python
accounting = AccountingConvention(
    transaction_scope="domestic",
    import_treatment="competitive",
    trade_representation="embedded",
    external_flow_scope="international",
    inflow_sign="negative",
    outflow_sign="positive",
    input_representation="complete",
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

`ioaudit` は、交易ベクトルが存在するという理由だけで輸入処理や会計式を推測しません。

### 競争輸入の符号規約

`domestic/competitive` では、`inflow_sign="negative" | "positive" | "unknown"` を使用します。

- `negative`: 流入ベクトルを符号付きの負値として扱う
- `positive`: 流入ベクトルを正の規模として扱う
- `unknown`: 符号を推測せず、影響する産出側の会計診断を `SKIPPED` にする

`import_treatment="none"` または `transaction_scope="total"` では、流入の符号は会計計算に適用されません。`trade_representation="unknown"` の場合は `Y` との関係を推測せず、影響する産出側の会計診断を `SKIPPED` にします。

## 投入側表現

`V` だけでは投入側の会計恒等式が成立せず、購入部門別の外部調整が必要な表では、`input_representation="adjustments_required"` を明示します。

調整値は符号込みで、`(n,)` または購入部門を列に持つ `(m, n)` として指定できます。

```python
accounting = AccountingConvention.domestic_competitive(
    trade_representation="embedded",
    input_representation="adjustments_required",
)

io = IOSystem(
    Z=Z,
    x=x,
    sectors=sectors,
    Y=Y,
    V=V,
    input_adjustments=adjustments,
    accounting=accounting,
)
```

投入側の外部調整は `input_adjustments` に一本化しています。`input_representation="unknown"` では、`V` が投入側を完全に説明するのか、外部調整を要するのかを推測しません。

2次元の `input_adjustments` では、DataFrame の列が購入部門を表します。列ラベルが `sectors` と一致しない場合、位置だけを頼りに加算せず、投入側の会計診断を `SKIPPED` にします。Unicode幅や空白を正規化した後にだけ一致する場合は、指定された順序で値を使用し、警告を記録します。

同じラベル方針は `Z`、`x`、`Y`、`V`、`TradeFlows` にも適用されます。正規化後にも不一致が残る場合は、位置だけを頼りに下流計算を行わず、影響する診断だけを `SKIPPED` にします。`TradeFlows` と `input_adjustments` の不備は、表本体の構造とは分けて `structure.supporting_status` に記録します。

## TradeFlows

全国表・地域表の外部フローは `TradeFlows` で明示します。`imports` / `exports` の個別引数は、v0.1 の `IOSystem` API にはありません。

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

同じ側で合算表現と分割表現を同時に指定した場合は、両者を加算せず、矛盾として扱います。

`external_flow_scope` は `international`、`interregional`、`both`、`unknown` のいずれかを指定します。`trade_representation` は `embedded`、`outflows_in_Y`、`separate`、`unknown` から選びます。

交易ベクトルは供給・需要側のフローとして扱い、購入部門別の外部投入として自動的に流用することはありません。

## 会計許容差

公表された産業連関表では、表示単位による丸め残差が生じることがあります。許容値を明示すると、完全一致と丸めの範囲内にある残差を区別できます。

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

会計診断は次のように分類されます。

- 完全一致: `PASS` + `residual_class="exact"`
- 許容差を指定せず非ゼロ残差がある: `AVAILABLE` + `residual_class="nonzero"`
- 非ゼロ残差が許容範囲内にある: `PASS` + `residual_class="rounding_level"`
- 残差が許容範囲を超える: `FAIL` + `residual_class="outside_tolerance"`

指定した許容差は provenance に保存されます。入力値そのものは変更されません。

## 外部参照との比較

既存の技術係数行列や Leontief 逆行列がある場合は、`A_reference` / `L_reference` として指定できます。

```python
io = IOSystem(
    Z=Z,
    x=x,
    sectors=sectors,
    A_reference=A_ref,
    L_reference=L_ref,
)
```

`ioaudit` は、内部で再計算した行列と外部参照を、shape、labels、数値差にもとづいて比較します。

参照行列の診断は、完全一致なら `PASS`、数値差はあるものの比較可能なら `AVAILABLE`、shape・label・非数値などの明示的な不整合があれば `FAIL`、参照行列が未指定または計算対象の行列が利用できなければ `SKIPPED` です。

任意指定の参照行列が不正でも、既定の `report.passed()` では表本体の判定を失敗させません。参照行列の形式不備を明示的に判定条件へ含める場合は `fail_on_invalid_reference=True` を指定します。数値差そのものを CI の判定条件にする場合は、`reference.A.relative_difference` などに閾値を明示できます。

## メタデータと provenance

表の意味を後から確認できるよう、メタデータを保持できます。

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

各監査には `report.provenance` が付き、主に次の情報を記録します。

- ioaudit のバージョン
- 入力データの SHA-256 ハッシュ
- 指定した数値計算方法
- 実際に選択された数値計算方法
- 会計許容差
- 桁違い診断の設定
- 適用した閾値
- 監査実行時刻

## 区切りテキストの事前診断

`IOSystem` を構築する前に、`inspect_csv()` / `inspect_delimited()` で区切りテキストを確認できます。結果型は `DelimitedFileReport` です。

```python
from ioaudit import inspect_csv

raw_report = inspect_csv(
    "io.csv",
    delimiter=",",
    encoding="cp932",
)

print(raw_report.summary())
```

主な診断対象は次のとおりです。

- 文字エンコーディング / BOM
- 区切り文字
- 空行
- 列数の不一致
- 空または重複したヘッダー
- 行末の余分な区切り文字
- 引用符の異常
- 不要な空白
- 数値として読めないトークン
- NaN / Inf に見えるトークン
- 引用符で囲まれていない桁区切りらしきパターン
- 注記行
- ファイル途中で再出現した見出し

タイトルや出典などの前文がある場合は、`header_line`、`preamble_rows`、`header_continuation_rows` として位置を報告します。行ラベル用の先頭列でヘッダーが空欄の場合は `leading_empty_headers` に記録します。表本体で期待される列数に満たない1列だけの行は、既知の注記でなければ `possible_truncated_rows` と列数不一致として記録します。

これらは診断情報であり、桁区切りの変換、行列範囲の自動確定、脚注・合計行の削除、`Z`・`x`・`Y`・`V` の自動抽出は行いません。

```text
ファイル診断
    ↓
呼び出し側でパース
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

CI や自動処理では、監査結果を判定条件として利用できます。

```python
report.raise_for_status()
```

会計相対残差を明示的な条件にする場合は、例えば次のように指定します。

```python
report.raise_for_status(
    max_relative_residual=1e-4,
)
```

`report.passed()` と `report.raise_for_status()` は同じ判定ルールを利用します。既定ではスペクトル半径に `1.0` の上限を適用し、任意の診断が利用できないという理由だけでは失敗にしません。

投入側・産出側の両方の会計診断と、その後の数値診断が利用可能であることを要求する場合は、次を使用します。

```python
report.passed(require_complete=True)
report.raise_for_status(require_complete=True)
```

特定の診断だけを必須にする場合は、レポート内のパスを指定できます。

```python
report.passed(
    require_available=["accounting.output_balance", "stability"]
)

report.raise_for_status(
    require_available=["accounting.output_balance"]
)
```

`require_available` で指定した診断は、存在し、かつ `SKIPPED` または `FAIL` でないことが必要です。

## 数値計算ルート

```python
report = audit(io, numerical_method="auto")
```

`"auto"` を指定すると、入力サイズや疎行列かどうかに応じて dense / iterative の計算経路を選択します。選択された方法や近似に関する情報は `report.methods` と provenance に記録されます。

## 対象範囲

v0.1 は、**単一の対称産業連関表（symmetric input-output table; SIOT）に対する分析前診断**に限定しています。

供給・使用表（Supply and Use Tables; SUT）は、v0.1 では直接の監査対象ではありません。SUT から対称産業連関表へ変換済みのデータは監査できますが、SUT から IOT への変換自体は `ioaudit` の対象外です。

また、次の機能は提供しません。

- RAS / GRAS / KRAS
- 行列バランシング
- 表の自動修正
- 地域化
- 交易推計
- データのダウンロード
- Excel ファイルの自動解釈
- 部門の自動対応付け
- 表同士の比較
- 階層・集計診断
- 波及効果分析
- 乗数分析
- 構造分解分析
- 政策順位付け
- 可視化
- GUI

`ioaudit` は産業連関分析そのものを行うライブラリではありません。

**「この表を分析コードに渡してよいか」を診断するためのライブラリです。**

## インストール

現在の開発版は、リポジトリを clone したうえで次のようにインストールできます。

```bash
pip install -e .
```

Python 3.10 以上が必要です。

テスト用依存関係を含める場合は、

```bash
pip install -e ".[test]"
```

を利用できます。

## テスト

```bash
pytest
```

## ライセンス

MIT License.

---

# English

`ioaudit` is a Python library that uses `audit()` to check whether an input-output table is ready for analysis.

> **Diagnose, do not repair.**

`ioaudit` reports problems and ambiguity, but it does not silently transpose, rebalance, delete, rescale, or otherwise repair the supplied table. When required information is unavailable, the affected diagnostic is reported as `SKIPPED` rather than inferred.

## What it can do

- shape, numeric type, sector labels, and order of `Z`, `x`, `Y`, and `V`
- whether the rows and columns of `Z` may have been transposed
- possible total rows or columns, non-sector items, duplicate labels, and zero rows or columns
- input- and output-side accounting residuals under the declared convention
- whether subtotal columns or rows in `Y` / `V` may cause double counting
- whether trade flows and `input_adjustments` are safe to use in accounting checks
- technical coefficients `A`, spectral radius, invertibility of `I - A`, condition number, and the Leontief inverse
- differences between recalculated matrices and `A_reference` / `L_reference`
- possible 10x, 100x, or 1000x scale errors suggested by accounting residuals
- human-readable summaries, JSON/DataFrame export, and CI gates

CSV and other delimited files can be checked separately with `inspect_csv()`. The library does not infer the table range or sector definitions from a file.

## Quickstart

For the boundary between caller-side parsing and `IOSystem`, plus three complete integration examples, see the [integration guide](docs/integration-guide.md).

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
report.structure       # structure of Z/x/Y/V and labels
report.orientation     # orientation and transpose evidence
report.accounting      # input/output accounting residuals
report.zero_structure  # zero-output and zero-structure evidence
report.coefficients    # technical coefficients A
report.stability       # I-A, spectral radius, and condition number
report.reference       # differences from A/L references
report.signs           # locations and values of negative entries
report.scale           # possible scale-error evidence
report.components      # Y/V subtotal double-counting candidates
report.metadata        # year, unit, and semantic metadata
report.provenance      # input hash and execution settings
```

## Diagnostic statuses

`ioaudit` does not reduce every diagnostic to a simple boolean.

- `PASS`: no problem was identified under the declared conditions
- `FAIL`: an explicit inconsistency or configured threshold violation was identified
- `WARNING`: evidence or a candidate issue requires review
- `SKIPPED`: the available information is insufficient for a safe determination
- `AVAILABLE`: the calculation ran, but no pass/fail criterion was declared

When a non-zero accounting residual is within an explicitly declared rounding tolerance, it is reported as `status="PASS"` with `residual_class="rounding_level"`.

`SKIPPED` does not mean that the data passed. It means that `ioaudit` declined to infer missing semantics.

## What does ioaudit check?

### Structure

- whether `Z` is two-dimensional and square
- whether `x` and sector dimensions are aligned
- NaN, Inf, and non-numeric values
- row, column, and sector-label alignment
- sector-axis alignment for `Y`, `V`, `TradeFlows`, and `input_adjustments`
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

When `Y`, `V`, and an explicit accounting convention are available, `ioaudit` evaluates input- and output-side accounting residuals, including:

- sector-level residuals
- absolute residuals
- relative residuals
- MAE
- RMSE
- maximum residuals
- residual class

The plain `AccountingConvention()` is deliberately conservative. If semantic fields remain `"unknown"`, affected accounting checks are reported as `SKIPPED` rather than inferred.

### Zero-output and zero-structure diagnostics

`report.zero_structure` reports:

- zero-output sectors
- all-zero rows
- all-zero columns
- isolated sectors
- inconsistencies between zero output and transaction structure
- evidence of positive final demand for all-zero rows
- evidence of positive value added for all-zero columns

These are diagnostics for checking extraction and missing values. Rows and columns are not deleted or filled automatically.

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

Candidates are not removed automatically. If a subtotal candidate makes the correct component selection ambiguous, the corresponding output or input balance is reported as `SKIPPED`.

For component panels with at most 12 components, small subsets are also searched. Partial-subtotal candidates can include `subset_indices`, `subset_labels`, `subset_size`, and `sum_similarity`. For a two-component `Y` or `V`, an unlabeled numeric match alone is not treated as a subtotal.

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

`transaction_scope`, `import_treatment`, `trade_representation`, `external_flow_scope`, `inflow_sign`, `outflow_sign`, and `input_representation` default to `"unknown"`. Affected accounting checks are therefore `SKIPPED` rather than evaluated under an implicit convention.

Explicit presets are available for common accounting structures:

```python
accounting = AccountingConvention.domestic_competitive(
    inflow_sign="negative",
    trade_representation="outflows_in_Y",
    external_flow_scope="international",
    outflow_sign="positive",
    input_representation="complete",
)
```

Other presets include:

```python
AccountingConvention.domestic_noncompetitive()
AccountingConvention.total_transactions()
```

`domestic_competitive()` and `domestic_noncompetitive()` fix only the `transaction_scope` and `import_treatment` implied by their names. Trade representation, signs, and input completeness remain `"unknown"` unless explicitly declared.

`total_transactions()` fixes `transaction_scope="total"` and `import_treatment="none"`, but leaves `input_representation="unknown"` because the completeness of the supplied value-added block is source-table information.

A convention can also be declared fully explicitly:

```python
accounting = AccountingConvention(
    transaction_scope="domestic",
    import_treatment="competitive",
    trade_representation="embedded",
    external_flow_scope="international",
    inflow_sign="negative",
    outflow_sign="positive",
    input_representation="complete",
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

`ioaudit` does not infer import treatment or an accounting equation merely from the presence of trade vectors.

### Competitive-import sign convention

For `domestic/competitive`, use `inflow_sign="negative" | "positive" | "unknown"`.

- `negative`: the inflow vector is treated as a signed negative value
- `positive`: the inflow vector is treated as a positive magnitude
- `unknown`: no sign is inferred and the affected output-side accounting check is `SKIPPED`

With `import_treatment="none"` or `transaction_scope="total"`, the inflow sign is not applied. With `trade_representation="unknown"`, `ioaudit` does not infer the relationship between trade and `Y`, and the affected output-side accounting check is `SKIPPED`.

## Input-side representation

When `V` alone does not close the input-side identity and user-specific external adjustments are required, declare `input_representation="adjustments_required"`.

The signed adjustment can have shape `(n,)` or `(m, n)`, with purchasing sectors on columns in the two-dimensional form.

```python
accounting = AccountingConvention.domestic_competitive(
    trade_representation="embedded",
    input_representation="adjustments_required",
)

io = IOSystem(
    Z=Z,
    x=x,
    sectors=sectors,
    Y=Y,
    V=V,
    input_adjustments=adjustments,
    accounting=accounting,
)
```

Input-side external adjustments use the single `input_adjustments` field. With `input_representation="unknown"`, `ioaudit` does not infer whether `V` is complete or requires adjustment.

For a two-dimensional `input_adjustments` DataFrame, columns identify purchasing sectors. If the column labels do not match `sectors`, positional addition is skipped and the input-side accounting check is `SKIPPED`. If labels match only after Unicode and whitespace normalization, values are used in the declared order and a warning is recorded.

The same label policy applies to `Z`, `x`, `Y`, `V`, and `TradeFlows`. A mismatch that remains after normalization prevents positional downstream calculations and skips only the affected diagnostics. TradeFlows and input-adjustment issues are recorded in `structure.supporting_status`, separately from the core table structure.

## TradeFlows

External and interregional flows are supplied through `TradeFlows`. Separate `imports` / `exports` arguments are not part of the v0.1 `IOSystem` API.

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

Supplying combined and split representations on the same side is treated as a conflict rather than added together.

Declare `external_flow_scope` as `international`, `interregional`, `both`, or `unknown`. Choose `trade_representation` from `embedded`, `outflows_in_Y`, `separate`, or `unknown`.

Trade vectors are treated as supply/demand-side flows and are not automatically reused as user-specific external inputs.

## Accounting tolerance

Published input-output tables can contain residuals caused by displayed rounding. Declare a tolerance to distinguish exact agreement from a rounding-sized residual.

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

Accounting diagnostics are classified as follows:

- exact agreement: `PASS` + `residual_class="exact"`
- non-zero residual without a declared tolerance: `AVAILABLE` + `residual_class="nonzero"`
- non-zero residual within the declared tolerance: `PASS` + `residual_class="rounding_level"`
- residual outside the declared tolerance: `FAIL` + `residual_class="outside_tolerance"`

The selected tolerance is stored in provenance. Input values are never modified.

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

`ioaudit` compares internally calculated matrices with the supplied references using shapes, labels, and numerical differences.

A reference comparison is `PASS` for exact agreement, `AVAILABLE` for a numerical difference that can be compared, `FAIL` for explicit structural, label, or numeric invalidity, and `SKIPPED` when the reference is not supplied or the calculated matrix is unavailable.

Invalid optional references do not fail the core `report.passed()` gate by default. Use `fail_on_invalid_reference=True` to include reference validity explicitly. To gate the numerical difference itself, declare a threshold on a path such as `reference.A.relative_difference`.

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

Delimited text files can be inspected before constructing an `IOSystem` with `inspect_csv()` or `inspect_delimited()`. The result type is `DelimitedFileReport`.

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

For files with title or source preambles, `header_line`, `preamble_rows`, and `header_continuation_rows` report their locations. A blank leading stub header is recorded in `leading_empty_headers`. A one-field row inside the body is recorded in `possible_truncated_rows` and as a column-count anomaly unless it matches a recognized note or metadata row.

These are diagnostics only. `ioaudit` does not convert thousands separators, infer matrix ranges, delete notes or totals, or automatically extract `Z`, `x`, `Y`, and `V`.

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

`report.passed()` and `report.raise_for_status()` use the same gate rules. By default, a spectral-radius limit of `1.0` is applied, while optional diagnostics do not fail merely because they are unavailable.

Use `require_complete=True` when both accounting sides and downstream numerical diagnostics must be available:

```python
report.passed(require_complete=True)
report.raise_for_status(require_complete=True)
```

Selected report paths can be required explicitly:

```python
report.passed(
    require_available=["accounting.output_balance", "stability"]
)

report.raise_for_status(
    require_available=["accounting.output_balance"]
)
```

A path supplied to `require_available` must exist and must not be `SKIPPED` or `FAIL`.

## Numerical routes

```python
report = audit(io, numerical_method="auto")
```

With `"auto"`, `ioaudit` selects a dense or iterative numerical route according to input size and whether the matrix is sparse. The selected route and approximation metadata are recorded in `report.methods` and provenance.

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
