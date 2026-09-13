# Cross-table validation runbook

このディレクトリは、国別のExcelレイアウトをパッケージへ取り込まずに、実データ検証を再現するための記録です。rawファイルはサイズ、利用条件、再配布条件を考慮してGitへ含めません。必要なファイルを入手した利用者が、元資料を確認して同じ切り出しを行います。

## 共通手順

1. 出典資料で表の種類、年度、単位、価格評価、部門分類を確認する。
2. Excel・CSV・SDMXの見出し、注記、合計項目、欠測値を読み取り、分析対象の軸を決める。
3. `Z`、`x`、`Y`、`V`、または `use`、`make`、`final_demand`、`value_added` を呼び出し側で明示的に切り出す。
4. `PriceBasis` または `metadata["price_basis"]`、単位、分類を記録する。
5. 表形式に応じて `IOSystem`、`SUTSystem`、`MRIOSystem` を構築する。
6. `audit()`、`audit_sut()`、`audit_mrio()` を実行し、`summary()`、`to_json()`、`provenance`を保存する。
7. 許容差を使った場合は、表の表示単位と丸め方を根拠として記録する。ライブラリの既定値として丸め幅を設定しない。

検証結果の再実行ログは [`RESULTS.md`](RESULTS.md) に記録します。結果は、正方ブロックとして監査できた表、抽出前に留めた長形式・固定幅データ、会計側だけが利用できなかった表を分けて読みます。

## 参照行列との一致確認手順

`A_reference` や `L_reference` を比較する前に、監査対象の表と参照行列について、次の項目を出典資料とメタデータで確認します。

1. 表の種類と年度が一致しているか確認する。`IOSystem`か`SUTSystem`か、対象年と価格年が同じかを記録する。
2. `price_basis`が一致しているか確認する。生産者価格、購入者価格、基本価格などが異なる行列を、そのまま同一の参照値として比較しない。
3. 単位、通貨、換算基準が一致しているか確認する。単位が異なる場合は、変換後の値を別途用意し、元データを上書きしない。
4. 対称次元と分類が一致しているか確認する。`industry`と`product`、分類体系、集計レベルを記録する。
5. 部門ラベルと順序が一致しているか確認する。ラベル集合だけでなく、`sectors`と参照行列の行・列順を確認する。tupleやMultiIndexでは地域と部門の両方を照合する。
6. 国内・総取引の範囲、輸入の扱い、交易の埋め込み方が一致しているか確認する。`DOM`と`TOTAL`、domesticとimportedの混在を避ける。
7. 行列の定義と計算方法が一致しているか確認する。`A`の分母となる`x`、`L=(I-A)^{-1}`の定義、丸め処理、表示桁を資料で確認する。
8. 欠測値、非数値、ゼロ部門がないか確認する。欠測をゼロへ変換して参照比較を成立させない。

最低限の呼び出し側確認は、次のように値を変更せずに行えます。

```python
assert list(sectors) == list(A_reference.index)
assert list(sectors) == list(A_reference.columns)
assert metadata["price_basis"] == reference_metadata["price_basis"]
assert metadata["unit"] == reference_metadata["unit"]
```

確認できない項目がある場合は、数値差を計算できても、意味上の一致を断定しません。`ioaudit`はshape、ラベル、有限性、数値差を診断しますが、参照資料の価格基準・単位・計算定義を外部資料なしに推測しません。比較条件が揃わない場合は、参照診断を`SKIPPED`または条件付きの結果として記録します。

丸め許容差は、参照表の表示単位・表示桁・公表資料の注記から設定します。`accounting_tolerance`や参照比較のthresholdに、ライブラリ側の単位推測を持ち込まないでください。

共通のインストールと単体テストは次で確認できます。

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

国別の抽出処理は共通化しません。再現時には、下の表にあるファイルを同じ相対パスへ置き、記載した範囲・軸・モデルを照合します。ファイルがない場合も、出典、形式、切り出し条件を確認する手順自体は追えます。現在は、単一SIOTだけでなく、SUT、MRIO、長形式API、固定幅ファイル、旧形式`.xls`も検証対象に含めています。

## 検証マニフェスト

機械可読な対応表は [`manifest.json`](manifest.json) にあります。各項目の `raw_path` はローカルに保存したコピーの位置であり、Git管理される入力データを意味しません。

| 系統 | 表形式 | 使用モデル | 検証内容 |
| --- | --- | --- | --- |
| 日本・経産省/e-Stat | 縦長Output Table | 抽出前の構造診断 | 行・列コード、特殊分類、価格列、正方ブロック化の境界 |
| 日本・e-Stat API | 長形式Output Table | 抽出前の構造診断 | API応答、カテゴリ軸、単位、`-`欠測トークン、非正方データ |
| 東京都 | 2015年107部門表（旧`.xls`） | 抽出前の構造診断 | 107部門ブロック、合計列、付加価値・最終需要行の混在 |
| 英国 | product-by-product SIOT | `IOSystem` | `Z`、`x`、最終需要構成、付加価値、投入側調整、A/L参照 |
| 台湾 | purchaser-price SIOT | `IOSystem` | 163部門表の見出し、価格評価、産出側調整の明示指定 |
| 韓国 | producer-price SIOTと国内・輸入ブロック | `IOSystem` | 国内取引、輸入投入、A/L参照、符号と投入側調整 |
| 米国 | total-requirements matrix | `IOSystem`の参照・ファイル診断 | CSV/XLSX一致、これは取引表`Z`ではないことの確認 |
| 米国・BEA | 固定幅Make/Use/Requirements | 抽出前の構造診断 | row/column/value形式、固定幅、価格評価、丸め注記 |
| 米国・BLS | producer-price SUT | `SUTSystem` | 176部門、末尾の付加価値行・最終需要列、Makeの向き、丸め許容差 |
| OECD | SDMX長形式Use/Value added | `SUTSystem`へ整形 | `P1`、`P2`、`B1G`、活動軸、単位・価格基準の選択 |
| Eurostat | industry-by-industry SIOT | `IOSystem` | `DOM` / `TOTAL`ブロック、65部門の明示選択、スペクトル半径 |
| WIOD | 国別SUT | `SUTSystem` | 64商品×64産業、総供給と国内Makeの区別、丸め許容差 |

## 既知の切り出し条件と結果

### 日本・経産省/e-Stat

`external_validation/meti_2020/japan_2020_iot_108_producer_price.xlsx` は、108部門のOutput Tableを含む縦長ファイルです。Row Code、Column Code、Special Classification、価格評価列を確認します。同じコードの重複を含むため、ファイル全体を`Z`へ変換しません。出典資料に基づいて取引表ブロックを別途選び、選択後の配列を`IOSystem`へ渡す境界を確認します。

### 日本・e-Stat API

`external_validation/estat_api/0004047205.json` は、e-Stat APIのstatsDataId `0004047205`から取得した応答です。APIは成功応答を返しましたが、データは20行カテゴリ×24列カテゴリの480観測からなる長形式で、単位は100万円、値には`-`が含まれます。これを未解釈のまま`IOSystem`へ渡すと、構造診断が`FAIL`、係数・安定性が`SKIPPED`になりました。API取得が成功しても、そのまま`Z`へ渡せるとは限らないことを確認するケースです。

API仕様は[e-Stat API利用案内](https://www.e-stat.go.jp/api/api-info/e-stat-manual3-0)を参照します。カテゴリの意味、単位、欠測値、価格評価を確認してから、呼び出し側で正方ブロックを切り出します。

### 東京都・2015年表

`prefecture_2015_confirmed_candidates`の東京都候補は旧`.xls`形式で、シートは123行×141列です。部門コードを持つ107行と、合計・付加価値等の追加行、107部門の中間取引候補列と最終需要等の追加列が同じシートにあります。107×107の候補ブロックと中間需要合計列を確認しましたが、`x`や最終需要の列は自動選択していません。旧Excel形式の読み込み自体も、呼び出し側の前処理として扱います。

### 英国

`data_raw/iot2023product.xlsx` の `IOT`、`A`、`Leontief` シートを使います。product-by-productの内生部門ブロックをラベルで照合し、最終需要の集計列を重ねて渡さないようにします。`P3 S1` の集計を除き、個別構成項目を`Y`へ渡したケースでは、参照A/Lとdense・iterative経路を比較します。今回のローカルファイルではA参照は数値比較でき、Leontief参照には欠測・非数値が含まれたため、L参照だけ`FAIL`として局所化されました。表本体の構造・係数・安定性は継続して診断できます。

### 台湾

`data_raw/f110c08e.xlsx` の `F110C08e` シートは、購入者価格の163×163取引表です。単位、行・列コード、注記、合計項目を確認してから対象ブロックを選びます。購入者価格に伴うマージン・税などを別途扱う場合は、資料に基づく符号付き`output_adjustments`として渡し、`PriceBasis.PURCHASER`を記録します。交易フローと2次元の調整ブロックを併用する場合は、各調整項目を`output_adjustment_roles`で明示します。自動的な生産者価格変換は行いません。

### 韓国

`data_raw/2023_Input-Output tables_Producer＇s price_Large-Sized.xlsx` の `Transaction_domestic(producer)`、`Transaction_imported(producer)`、`Transaction(producer)`、`Input coefficients(dom)`、`ProductionInducement` を使います。国内中間取引と輸入投入を混同せず、購入部門別の輸入投入を`input_adjustments`として明示します。A/L参照は同じ部門順、価格評価、単位で構成されたものだけ比較します。

### 米国

`data_raw/Table.xlsx` と `data_raw/Table.csv` は同一の15部門total-requirements matrixとして照合します。これは中間取引行列`Z`ではないため、取引表として会計監査へ渡さず、ファイル診断と`L_reference`等の参照検証に使います。BEA/BLSのMake/UseはSUT形式として扱い、v0.1の`IOSystem`へ自動変換しません。

### 米国・BEA 2002 Benchmark

`data_raw/us_bea_2002_detail_redef.zip`は、BEAの2002年Benchmark Make/Use/Direct Requirements詳細資料です。Makeは4,773行、Useは57,131行、Direct Requirementsは185,311行で、いずれも見出しを含みます。付属資料に従って固定幅のrow/column/valueフィールドを確認し、producer's value、purchaser's value、margin項目の区別を保ったまま、必要なSUTまたはSIOTブロックを呼び出し側で作成します。付属READMEの、詳細値は丸めのため合計と一致しない場合があるという注意も、許容差設定の根拠として記録します。

### 米国・BLS 2035 projected tables

`data_raw/us_bls_input_output.zip`の付属資料で、`USE`は176商品×176産業の中間使用に、付加価値の末尾行と最終需要の末尾列を加えた177×177、`MAKE`は176×176、集計最終需要は176×11であることを確認しました。ファイル上の`MAKE`は産業×商品なので、`SUTSystem`へ渡す場合は呼び出し側で商品×産業へ明示的に転置します。2035年実質表を明示抽出し、`output_by_product_scope="domestic_output"`、単位million chained 2017 dollars、絶対・丸め許容差0.05を指定したところ、商品側・産業側・Make側の4会計が`PASS`になりました。許容差はBLS資料の小数丸めに対応する検証用設定で、ライブラリの既定値ではありません。

出典は[BEA Benchmark Input-Output Data](https://www.bea.gov/industry/benchmark-input-output-data)と[BLS Input-Output Matrix](https://www.bls.gov/emp/data/input-output-matrix.htm)です。

### OECD

`external_validation/oecd_icio_2025/oecd_sut_useva_2020.csv` はSDMX長形式です。`P1`（output）、`P2`（intermediate consumption）、`B1G`（gross value added）などの取引項目、地域、活動、単位、評価を選び、product×industryのブロックを明示的に整形します。長形式からの自動抽出は行いません。

### Eurostat

`external_validation/eurostat_figaro_2026/naio_10_cp1750_EU27_2022.json` から、定義を確認した65部門の`DOM`または`TOTAL`ブロックと`P1`産出を選びます。確認済みのスペクトル半径は`TOTAL=0.572781`、`DOM=0.489554`です。データセット全体を自動分類した結果ではありません。

### WIOD

`external_validation/wiod_2016/JPN_SUT_nov16.xlsx` のSUP/USEから64商品×64産業のUse、最終需要、付加価値、産業産出を選び、`SUTSystem`へ渡します。`SUP_bas`は輸入を含む総供給なので、国内Makeの行和との比較は`output_by_product_scope="total_supply"`としてスキップします。商品側の約112.91 million USDの差は、検証時に明示した`absolute=200.0`、`rounding_unit=200.0`の範囲で評価します。この許容差はライブラリの既定値ではありません。

## 境界

この記録は、抽出コードや国別アダプターの配布を意味しません。`ioaudit`へ渡す直前のデータ整形と意味の確認は利用者が担当します。rawファイルを自動取得、削除、修正、再配布する処理は行いません。
