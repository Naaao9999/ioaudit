# ioaudit

**産業連関表を分析する前に、表そのものを監査する Python ライブラリ。**

`ioaudit` は、産業連関表を分析コードに渡す前に、データ構造、会計整合性、行列の向き、ゼロ産出部門、合計列・行の混入、桁・単位ミスの候補、Leontief 系の数値安定性などを診断します。

> **Diagnose, do not repair. — 診断するが、自動修正しない。**

問題が見つかっても、`ioaudit` は表を勝手に転置・補正・削除・再スケールしません。必要な情報が不足している診断は、推測せず `SKIPPED` として扱います。

---

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
report.scale
report.components
report.metadata
report.provenance
```

---

## 何を診断するか

利用可能な入力に応じて、`audit()` は主に次を確認します。

### 構造

- `Z` が2次元・正方行列か
- `x` と部門数が整合しているか
- NaN / Inf / 非数値が含まれていないか
- 行・列・部門ラベルが整合しているか
- 重複ラベルがないか
- Unicode幅・空白の違いによる実質的な重複がないか
- 合計行・合計列や、非部門項目らしきラベルが混入していないか
- 完全一致する行・列がないか

### 行列の向き

- 行ラベルと列ラベルの対応
- 部門順序
- `x` のalignment
- 現在の向きと転置した場合の会計残差比較
- `possible_transpose`

転置の可能性を報告しても、行列を自動的に転置することはありません。

### 会計整合性

会計規約と `Y` / `V` が利用できる場合、投入側・産出側の残差を計算します。

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

- 技術係数行列 `A`
- 係数の有限性
- spectral radius
- `I - A` の可逆性
- condition number
- Leontief inverse の有限性

### 合計列・合計行の二重計上候補

`Y` の最終需要計や `V` の付加価値計など、他の構成要素を既に含んでいる可能性がある列・行を診断します。

```python
report.components.possible_subtotal_columns
report.components.possible_subtotal_rows
report.components.double_count_risk
```

subtotal候補が検出されても、`ioaudit` はその列・行を勝手に除外しません。曖昧な場合は、影響する会計診断を `SKIPPED` にします。

### 桁・単位ミスの候補

会計残差を利用して、10のべき乗による桁違いの候補を探索します。

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

候補は修正値ではなく、残差改善にもとづく診断上の証拠です。値を自動的に掛け直すことはありません。

---

## 会計診断

会計恒等式を監査する場合は、表の会計規約を `AccountingConvention` で明示します。

```python
from ioaudit import AccountingConvention

Y = np.array([[6.0], [7.0]])
V = np.array([[5.0, 8.0]])

io = IOSystem(
    Z=Z,
    x=x,
    sectors=["農業", "製造業"],
    Y=Y,
    V=V,
    accounting=AccountingConvention(
        transaction_scope="domestic",
        import_treatment="competitive",
        trade_representation="embedded",
    ),
)

report = audit(io)
```

`ioaudit` は、輸入ベクトルが存在するという理由だけで会計式を推測しません。表現が不明な場合は、無理に残差を計算せず該当診断を `SKIPPED` とします。

### 丸め誤差

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

---

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

交易が最終需要に含まれているのか、別掲なのか、不明なのかは `AccountingConvention` で宣言します。

```python
accounting = AccountingConvention(
    transaction_scope="domestic",
    import_treatment="competitive",
    trade_representation="outflows_in_Y",
    external_flow_scope="international",
    inflow_sign="negative",
    outflow_sign="positive",
)
```

`ioaudit` は交易表現を自動推定しません。合算表現と分割表現が同時に与えられるなど、二重計上の可能性がある場合は該当診断を `SKIPPED` にします。

---

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

`ioaudit` が再計算した結果とのshapeや数値差を診断できます。

---

## Metadata と provenance

表の意味を再現できるよう、metadataも保持できます。

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

主に次の項目の有無を確認します。

- `year`
- `unit`
- `price_basis`
- `currency`
- `valuation`

各監査には `report.provenance` が付きます。

主な記録内容は、

- ioaudit version
- input SHA-256 hash
- requested numerical method
- selected numerical method
- accounting tolerance
- scale diagnostic settings
- applied thresholds
- audit timestamp

です。

---

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

例えば次のような問題を報告します。

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

---

## 結果の利用

人が読む要約だけでなく、後続処理向けにも出力できます。

```python
report.summary()
report.to_dict()
report.to_json()
report.to_dataframe()
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

---

## 数値計算ルート

```python
report = audit(io, numerical_method="auto")
```

`auto` は入力サイズや疎行列かどうかに応じて dense / iterative route を選択します。選択した方法や推定の有無は `report.methods` と provenance に記録されます。

---

## 設計原則

### Diagnose, do not repair

`ioaudit` は次の処理を自動では行いません。

- 不整合表のバランシング
- 合計行・合計列の削除
- 行列の転置
- 符号の変更
- 桁ミス候補の補正
- 不明な会計規約の推測

監査結果は、表を修正する命令ではなく、分析前に確認すべき証拠として返されます。

---

## 対象範囲

v0.1 は、**単一の産業連関表に対する分析前診断**に限定しています。

次の機能は対象外です。

- RAS / GRAS / KRAS
- 行列バランシング
- 表の自動修正
- 地域化
- 交易推計
- データダウンロード
- Excelの自動解析
- 部門自動対応
- 表比較
- 階層・集計診断
- 経済波及効果分析
- 乗数分析
- 構造分解分析
- 政策ランキング
- 可視化
- GUI

`ioaudit` は産業連関分析そのものを行うライブラリではありません。

**「この表を分析コードに渡してよいか」を診断するためのライブラリです。**

---

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

---

## Tests

```bash
pytest
```

---

## License

MIT License.
