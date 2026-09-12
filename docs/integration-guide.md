# ioaudit integration guide

このガイドは、公開されたCSV・Excel・統計APIなどのデータを `ioaudit` に渡すまでの責務分担を説明します。

`ioaudit` は、表を自動的に読み替えたり修正したりしません。利用者が資料を確認して `Z`、`x`、`Y`、`V` と部門ラベルを用意し、会計上の意味を宣言したうえで `IOSystem` を作成します。その後の構造・会計・係数・数値安定性の診断を `audit()` が実行します。

## 全体の流れ

```text
公表データの取得
    ↓  利用者のadapter / parser
Z, x, Y, V, sectors の切り出し
    ↓  資料に基づく意味の確認
AccountingConvention / TradeFlows / input_adjustments / output_adjustments
    ↓
IOSystem
    ↓
audit()
    ↓
report の確認・CI gate
    ↓
利用者のIO分析
```

| 段階 | 利用者が担当すること | `ioaudit` が担当すること |
| --- | --- | --- |
| 元データ取得 | Excel、CSV、統計APIなどから取得 | 取得しない |
| 表の切り出し | `Z`、`x`、`Y`、`V`、部門ラベルを特定 | 自動抽出しない |
| 意味の確認 | 国内取引か総取引か、交易の格納方法、符号、`V` の完全性、産出側調整の有無を資料で確認 | 推測しない |
| Python化 | NumPy配列、pandas DataFrame等へ変換 | 受け取った値を変更しない |
| IOSystem構築 | `IOSystem(...)` を作成 | 構造を保持する |
| 監査 | `audit(io)` を呼び出す | 診断結果を返す |
| 判断・修正 | `WARNING`、`AVAILABLE`、`SKIPPED`を確認し、必要なら抽出処理を修正 | 自動修正しない |
| IO分析 | 検証済みの表を分析コードへ渡す | 波及効果分析等は行わない |

## 1. 最小監査

会計規約がまだ確定していなくても、構造、係数、Leontief系などを監査できます。

```python
import numpy as np

from ioaudit import IOSystem, audit

Z = np.array([
    [10.0, 2.0],
    [3.0, 8.0],
])
x = np.array([18.0, 18.0])
sectors = ["agriculture", "manufacturing"]

io = IOSystem(Z=Z, x=x, sectors=sectors)
report = audit(io)

print(report.summary())
print(report.coefficients.A)
print(report.stability.spectral_radius)
```

`Y`、`V`、`AccountingConvention`を渡していない会計診断は、情報を推測せず `SKIPPED` になります。

## 2. 総取引表

`total_transactions()` は、表が総取引範囲であることと、別建ての輸入処理がないことを宣言します。投入側で `V` が完全かどうかは名前から決まらないため、presetはそこを推測せず `SKIPPED` にします。

```python
import numpy as np

from ioaudit import AccountingConvention, IOSystem, audit

Z = np.array([
    [1.0, 0.5],
    [0.2, 1.5],
])
Y = np.array([
    [2.5],
    [2.3],
])
x = np.array([4.0, 4.0])
V = np.array([2.8, 2.5])

io = IOSystem(
    Z=Z,
    x=x,
    sectors=["A", "B"],
    Y=Y,
    V=V,
    accounting=AccountingConvention.total_transactions(),
)
report = audit(io)

assert report.accounting.output_balance.status == "PASS"
assert report.accounting.input_balance.status == "SKIPPED"
```

投入側の完全性が資料で確認できる場合は、明示的な規約を作成します。

```python
accounting = AccountingConvention(
    transaction_scope="total",
    import_treatment="none",
    trade_representation="embedded",
    input_representation="complete",
)
```

## 3. 国内表、交易、投入側調整

次の例は、`Y` に域内最終需要と流出が含まれ、流入が別の負値ベクトルで与えられ、投入側には購入部門別の調整を加える表です。実際の表でこの構造を使う場合は、必ず統計資料の定義を確認してください。

```python
import numpy as np

from ioaudit import (
    AccountingConvention,
    IOSystem,
    TradeFlows,
    audit,
)

Z = np.array([
    [1.0, 0.5],
    [0.2, 1.5],
])
x = np.array([4.0, 4.4])
Y = np.array([3.0, 3.0])
V = np.array([2.2, 2.1])
imports = np.array([-0.5, -0.3])  # signed negative inflows
input_adjustments = np.array([0.6, 0.3])

accounting = AccountingConvention.domestic_competitive(
    inflow_sign="negative",
    trade_representation="outflows_in_Y",
    external_flow_scope="international",
    input_representation="adjustments_required",
)

io = IOSystem(
    Z=Z,
    x=x,
    sectors=["A", "B"],
    Y=Y,
    V=V,
    trade=TradeFlows(international_imports=imports),
    input_adjustments=input_adjustments,
    accounting=accounting,
)
report = audit(io)

assert report.accounting.output_balance.status == "PASS"
assert report.accounting.input_balance.status == "PASS"
```

`TradeFlows` の交易ベクトルと `input_adjustments` は別の概念です。産品別・供給側の流入を、購入部門別の投入調整として自動的に再利用しません。

## 4. 購入者価格表と産出側調整

購入者価格表などで、`Y` と交易フローに加えて商業マージン、運輸マージン、税、輸入調整などを産出側の別項目として持つ場合は、`output_adjustments` にまとめて渡します。各値は会計式へ直接加える符号付き値として、利用者が資料に基づいて作成します。`ioaudit` は生産者価格への変換や符号の推測を行いません。

```python
import numpy as np
import pandas as pd

from ioaudit import AccountingConvention, IOSystem, TradeFlows, audit

sectors = ["A", "B"]
Z = np.array([[10.0, 2.0], [3.0, 8.0]])
Y = np.array([[8.0], [7.0]])
V = np.array([[5.0, 8.0]])
imports = np.array([1.0, 1.0])
output_adjustments = pd.DataFrame(
    [[-1.0], [1.0]],
    index=sectors,
    columns=["value-added tax adjustment"],
)
x = np.array([18.0, 18.0])

accounting = AccountingConvention.domestic_competitive(
    inflow_sign="positive",
    trade_representation="outflows_in_Y",
    external_flow_scope="international",
    input_representation="complete",
    output_representation="adjustments_required",
)

io = IOSystem(
    Z=Z,
    x=x,
    sectors=sectors,
    Y=Y,
    V=V,
    trade=TradeFlows(international_imports=imports),
    output_adjustments=output_adjustments,
    accounting=accounting,
)
report = audit(io)
assert report.accounting.output_balance.status == "PASS"
```

`output_adjustments` は `(n,)` または行が部門・列が調整項目の `(n, k)` です。`output_representation="adjustments_required"` でブロックがない場合、形状・ラベルが不正な場合、または小計候補がある場合は、産出側会計を `SKIPPED` にします。`TradeFlows` と同じ輸入・輸出項目を重ねた場合や、項目ラベルがなく交易との重複を排除できない場合も、安全のため使用しません。

## 会計規約の選び方

presetが確定するのは、名前から直接分かる範囲だけです。

```text
国内取引の表
├─ competitive imports  → AccountingConvention.domestic_competitive()
└─ noncompetitive imports → AccountingConvention.domestic_noncompetitive()

総取引の表
└─ AccountingConvention.total_transactions()
```

その後、資料から次を確認してフィールドを明示します。

- `trade_representation`: 交易が `Y` に含まれるか（`embedded`、`outflows_in_Y`、`separate`）
- `external_flow_scope`: 国際交易、地域間交易、または両方か
- `inflow_sign` / `outflow_sign`: 正の金額か、符号付きベクトルか
- `input_representation`: `V` だけで投入側が閉じるか、`input_adjustments` が必要か
- `output_representation`: `Y` と交易だけで産出側が閉じるか、`output_adjustments` が必要か

不明な項目は `"unknown"` のままにしてください。影響する診断は `SKIPPED` になります。

## ラベルと向き

`Z` の行・列、`x`、`Y` の行、`V` の列、交易ベクトル、`input_adjustments` の購入部門列、`output_adjustments` の行は `sectors` と同じ順序で用意します。

- 完全一致ならそのまま使用します。
- Unicodeや空白の正規化後だけ一致する場合は、値を指定順序で使用し、警告を記録します。
- 正規化後も一致しない場合は、位置ベースで使用せず、影響する診断を `SKIPPED` にします。

転置や部門順序の変更は自動で行われません。

## よくある `SKIPPED` の原因

| 診断 | 代表的な原因 |
| --- | --- |
| `accounting.output_balance` | `Y` 不在、交易表現・流入符号が不明、Y/Vにsubtotal候補がある、ラベル不一致 |
| `accounting.input_balance` | `V` 不在、`input_representation="unknown"`、投入側調整が不足、ラベル不一致 |
| `coefficients` / `stability` | `Z`・`x` のshape、非数値、重複部門ラベル、順序不一致 |
| `reference` | 参照行列のshape、値、ラベルに問題がある |
| `scale` のセル診断 | 丸め単位などの `accounting_tolerance` が未指定 |

`SKIPPED` は自動的な合格判定ではありません。分析に必要な診断が利用可能かを確認する場合は、次のように明示します。

```python
report.raise_for_status(
    require_available=[
        "accounting.output_balance",
        "accounting.input_balance",
        "stability.spectral_radius",
    ]
)
```

## ファイル診断との境界

CSV等の区切りテキストは、IOSystemを作る前に診断できます。

```python
from ioaudit import inspect_csv

raw_report = inspect_csv("table.csv", encoding="cp932")
print(raw_report.summary())
```

これはdelimiter、encoding、列数不一致、空行、引用符、数値として読めないトークン等を調べます。`ioaudit` はファイルのどの部分が `Z` や `Y` なのかを決めないため、パースと表の切り出しは利用者のadapterで行います。

## English summary

The caller owns data acquisition, parsing, table extraction, and semantic interpretation. The caller must provide `Z`, `x`, `Y`, `V`, and sector labels in an explicit order, then declare the accounting convention. `ioaudit` validates the supplied representation and returns diagnostics; it does not transpose, drop totals, infer trade treatment, balance, or rescale the table.

The three examples above cover the intended entry points:

1. a minimal structural and numerical audit;
2. a total-transactions table, where input completeness remains unknown unless declared;
3. a domestic table with explicit trade flows and user-specific input adjustments.

Use `SKIPPED` as a signal that the relevant information or semantic declaration is missing, and use `require_available` when a downstream analysis requires a particular diagnostic to have run.
