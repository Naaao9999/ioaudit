---
title: "産業連関表を分析に渡す前に監査するPythonライブラリ ioaudit を作った"
emoji: "🔍"
type: "tech"
topics: ["python", "データ分析", "統計", "研究開発", "github"]
published: false
---

# はじめに

産業連関表は、産業間の取引関係を使って、ある需要や投資が各産業の生産や付加価値にどの程度波及するかを推計したり、地域経済の産業構造やサプライチェーン上の依存関係を分析したりするときに使われます。環境負荷や雇用などのデータを組み合わせれば、需要に伴うCO2排出量や雇用誘発といった分析にも使えます。

こうした分析では、CSVやExcelから産業連関表を読み込み、`numpy` の配列に変換すれば、技術係数行列やLeontief逆行列を比較的簡単に計算できます。一方で、分析に使う表の構造を誤って解釈していても、配列の形が合っていれば計算自体はそのまま実行できてしまいます。

たとえば、行と列を逆に解釈している、合計行を部門として取り込んでいる、最終需要の構成項目と最終需要計を重複して足している、といった問題があっても、必ずしもPython上のエラーにはなりません。輸入・移入の符号、価格評価、単位の違いも同様で、コードは正常に動いていても分析結果の意味が変わることがあります。

こうした入力上の問題を分析前に確認するため、産業連関表の構造や会計関係を監査するPythonライブラリ `ioaudit` を作りました。

GitHub: https://github.com/Naaao9999/ioaudit

現在は単一の対称産業連関表（SIOT）を対象に、入力構造、行列の向き、会計残差、小計・合計の混入、技術係数、Leontief逆行列計算の数値安定性などを確認できます。

## e-Statから取得した表を分析用に整える

[e-Stat](https://www.e-stat.go.jp/) のAPIや公開ファイルを使えば、必要な統計データを取得できます。ただし、公的統計のExcelやCSVは、そのまま機械処理することを前提に作られているとは限りません。

表題や注記、複数行の見出し、結合セル、小計・合計行など、人が読むときのレイアウトを優先した構成も多く、分析に使うには必要な範囲を切り出して表の構造を整理する必要があります。同じ統計でも、年度、表の種類、地域、単位、価格評価、部門分類が異なるファイルが並んでいます。APIを使う場合も、部門コードや項目コードを確認しながら、取得した値が分析上のどの要素に対応するかを組み立てる必要があります。

産業連関分析に使う場合は、どの表・年度・シートを対象にするかに加えて、少なくとも次の対応を確定します。

* どの行と列が内生部門か
* どのベクトルが生産額 `x`、最終需要 `Y`、付加価値 `V` か
* 行と列の部門順が一致しているか
* 合計・小計・控除・注記をどう扱うか
* 単位、価格評価、輸入・移入の扱いは何か

ここを取り違えると、別の部門の値や合計列を含んだ配列でも、そのまま後続の行列計算に渡せます。

`ioaudit` はExcelやAPIから分析範囲を自動で切り出すライブラリではありません。切り出しは呼び出し側で行い、`ioaudit` には分析用に作成した `Z`、`x`、`Y`、`V` と部門ラベルを渡します。その入力が産業連関表として妥当な構造になっているかを、計算前に確認します。

## 入力を修正せずに診断する

`ioaudit` では `diagnose, do not repair` を基本方針にしています。

転置されている可能性、合計列や小計列らしい項目、桁違いの可能性、会計残差、数値的に不安定な行列などを検出してレポートしますが、元の入力データは自動で変更しません。

産業連関表は、公表主体や表の種類によって項目の意味や符号の扱いが異なります。たとえば負値が異常値とは限らず、輸入や控除項目として意図的に負値が使われている場合があります。ライブラリ側で意味を推測して修正すると、正しい値まで変更する可能性があります。

そのため、`ioaudit` は問題の候補と判断材料を返し、入力を修正するかどうかは利用者が元資料を確認して決める設計にしています。診断に必要な情報が不足している場合は、無理に判定せず理由とともに `SKIPPED` を返します。

## 最小構成

最低限、`Z`、`x`、部門ラベルがあれば監査できます。

```python
import numpy as np

from ioaudit import IOSystem, audit

Z = np.array([
    [10.0, 2.0],
    [3.0, 8.0],
])

x = np.array([18.0, 18.0])

sectors = ["agriculture", "manufacturing"]

io = IOSystem(
    Z=Z,
    x=x,
    sectors=sectors,
)

report = audit(io)

print(report.summary())
```

この構成でも、入力の形状やラベル、ゼロ行・ゼロ列、技術係数、`I - A` の可逆性や条件数などを確認できます。

監査結果は `AuditReport` にまとめられます。

```python
print(report.structure)
print(report.orientation)
print(report.accounting)
print(report.coefficients)
print(report.stability)
print(report.components)
print(report.metadata)
print(report.provenance)
```

このほか、負値、桁違い候補、外部参照行列との差などを確認する診断もあります。

診断状態は `PASS`、`AVAILABLE`、`WARNING`、`FAIL`、`SKIPPED` の5種類です。`AVAILABLE` は値自体は計算できるものの、合否を決める条件が指定されていない場合に使います。

たとえば会計残差を計算できても、その残差が許容可能かどうかは、表の単位や丸め方法によって変わります。この場合は残差を `AVAILABLE` として返し、利用者が許容差を指定した時点で判定できるようにしています。

## 会計規約の明示

`Y` や `V` を使って会計整合性を確認する場合は、その表がどのような会計構造を持つかを `AccountingConvention` で指定します。

```python
from ioaudit import AccountingConvention

accounting = AccountingConvention.domestic_competitive(
    inflow_sign="negative",
    trade_representation="outflows_in_Y",
    external_flow_scope="international",
    input_representation="complete",
    output_representation="complete",
)
```

ここで指定するのは国名ではなく、表そのものの構造です。たとえば、`Z` が国内取引を表すのか総取引を表すのか、輸入が競争輸入か非競争輸入か、輸出・移出が `Y` に含まれているか、輸入・移入が正値か負値か、`V` だけで投入側の会計式が閉じるか、といった点を元資料に基づいて指定します。

`ioaudit` は指定された会計規約に沿って会計診断を行います。必要な規約が指定されていない診断は `SKIPPED` とし、ライブラリ側で表の意味を補完しません。

## 交易フローと調整項目

輸入・輸出、移入・移出などの交易フローは `TradeFlows` にまとめて渡せます。

```python
from ioaudit import TradeFlows

trade = TradeFlows(
    interregional_inflows=interregional_inflows,
    international_imports=international_imports,
    interregional_outflows=interregional_outflows,
    international_exports=international_exports,
)
```

移入と輸入、移出と輸出が分かれていない表では、合算値として渡すこともできます。

```python
trade = TradeFlows(
    combined_inflows=inflows,
    combined_outflows=outflows,
)
```

購入者価格表では、商業マージン、運輸マージン、税、輸入調整などを産出側の会計式に加える場合があります。こうした項目は `output_adjustments` として明示的に渡します。

```python
io = IOSystem(
    Z=Z,
    x=x,
    sectors=sectors,
    Y=Y,
    V=V,
    trade=trade,
    output_adjustments=output_adjustments,
    accounting=accounting,
)
```

`output_adjustments` には、会計式にそのまま加える符号付きの値を渡します。各項目の意味や符号は `ioaudit` が推測せず、元資料に基づいて呼び出し側で指定します。

## 小計・合計の二重計上

公表表を配列に変換するときに起こりやすい問題の一つが、小計や合計の混入です。

たとえば `Y` に次の列が含まれているとします。

```text
household consumption
government consumption
investment
exports
final demand total
```

`final demand total` が上の4項目の合計であれば、5列すべてを足すと最終需要を二重計上します。`V` についても、付加価値の構成項目と付加価値計を同時に含めれば同じ問題が起こります。

`ioaudit` ではラベルだけでなく数値関係も使って、小計・合計らしい列や行を候補として抽出します。

```python
report.components.possible_subtotal_columns
report.components.possible_subtotal_rows
report.components.double_count_risk
```

ここでも候補を自動的に削除することはありません。元表の定義や注記を確認した上で、どの項目を分析に使うかを利用者が決めます。

## 丸め誤差

公表されている産業連関表では、表示単位や丸め処理によって会計残差が生じることがあります。そのため、残差がゼロでないという理由だけで不整合と判定すると、正常な表まで異常扱いする可能性があります。

`ioaudit` では、必要に応じて監査時に許容差を指定できます。

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

指定した丸め幅に対応する残差は、完全一致とは区別して `residual_class="rounding_level"` として記録します。

許容可能な残差の大きさは表の単位や公表方法によって異なるため、ライブラリ側では固定せず、利用者が指定した条件に基づいて評価します。

## CSV自体の確認

ExcelやCSVから `Z`、`x`、`Y`、`V` を切り出す処理は呼び出し側で行いますが、その前段階としてCSVファイル自体の状態を確認する機能も用意しています。

```python
from ioaudit import inspect_csv

raw_report = inspect_csv(
    "table.csv",
    delimiter=",",
    encoding="cp932",
)

print(raw_report.summary())
```

`inspect_csv()` では、列数の不一致、空行、重複ヘッダー、引用符の異常、未引用の桁区切りらしいパターン、数値以外のトークンなどを確認します。

想定している処理の流れは次の通りです。

```text
official file
    ↓
caller-side parser / adapter
    ↓
Z, x, Y, V, sectors
    ↓
IOSystem
    ↓
audit()
```

ファイルが構文上正しく読めるかという問題と、ファイル内の各範囲が産業連関表上で何を意味するかという問題は分けて扱っています。

## 表ごとの差を会計構造として扱う

開発中は、日本、英国、韓国、米国、台湾、EU系の公表表を使って動作を確認しました。

産業連関表は公表主体によって構造が異なります。industry-by-industry と product-by-product の違い、`Y` に輸出や小計が含まれるかどうか、輸入が正値か負値か、購入者価格の調整項目が別掲されているか、投入側の会計式に追加項目が必要か、といった違いがあります。

`ioaudit` では、こうした差を「日本の表ならこの処理」「米国の表ならこの処理」といった国別の分岐として実装していません。`AccountingConvention`、`TradeFlows`、調整項目、`metadata` を使って、表の構造そのものを指定します。

```python
io = IOSystem(
    Z=Z,
    x=x,
    sectors=[
        ("JPN", "CPA_A01"),
        ("JPN", "CPA_C10"),
    ],
    metadata={
        "year": 2023,
        "unit": "million_eur",
        "price_basis": "producer",
        "symmetric_dimension": "product",
        "classification": "CPA",
    },
)
```

表ごとの差は読み込み段階で確認し、監査の入口は `IOSystem` と `audit()` にそろえる構成です。

## 今後

まずは `v0.1` として、単一SIOTの監査に対象を絞ってAPIを固めます。

`v0.2` では現在のモデルを維持しながら、価格評価、単位・通貨・価格年、為替・PPP基準、国×部門の複合識別子、部門コード、分類体系、crosswalk など、表の意味をより明示的に持たせる予定です。CO2、雇用、エネルギーなどの satellite account や、sparse 行列、大規模表への対応も検討しています。

MRIOやSUTはSIOTとはデータ構造そのものが異なるため、`IOSystem` に引数を追加して吸収するのではなく、別のデータモデルとして扱う方針です。

## おわりに

産業連関表は、計算に入る前の確認事項が多く、しかも間違っていてもそのまま計算できてしまうことがあります。`ioaudit` は、その確認を毎回手作業で済ませず、ある程度同じ手順でチェックできるようにするために作りました。

まだ単一SIOT向けの `v0.1` ですが、実際の公表表で使いながら、必要な診断を追加していく予定です。

GitHub: [https://github.com/Naaao9999/ioaudit](https://github.com/Naaao9999/ioaudit)
