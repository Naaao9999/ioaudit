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

共通のインストールと単体テストは次で確認できます。

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

国別の抽出処理は共通化しません。再現時には、下の表にあるファイルを同じ相対パスへ置き、記載した範囲・軸・モデルを照合します。ファイルがない場合も、出典、形式、切り出し条件を確認する手順自体は追えます。

## 検証マニフェスト

機械可読な対応表は [`manifest.json`](manifest.json) にあります。各項目の `raw_path` はローカルに保存したコピーの位置であり、Git管理される入力データを意味しません。

| 系統 | 表形式 | 使用モデル | 検証内容 |
| --- | --- | --- | --- |
| 日本・経産省/e-Stat | 縦長Output Table | 抽出前の構造診断 | 行・列コード、特殊分類、価格列、正方ブロック化の境界 |
| 英国 | product-by-product SIOT | `IOSystem` | `Z`、`x`、最終需要構成、付加価値、投入側調整、A/L参照 |
| 台湾 | purchaser-price SIOT | `IOSystem` | 163部門表の見出し、価格評価、産出側調整の明示指定 |
| 韓国 | producer-price SIOTと国内・輸入ブロック | `IOSystem` | 国内取引、輸入投入、A/L参照、符号と投入側調整 |
| 米国 | total-requirements matrix | `IOSystem`の参照・ファイル診断 | CSV/XLSX一致、これは取引表`Z`ではないことの確認 |
| OECD | SDMX長形式Use/Value added | `SUTSystem`へ整形 | `P1`、`P2`、`B1G`、活動軸、単位・価格基準の選択 |
| Eurostat | industry-by-industry SIOT | `IOSystem` | `DOM` / `TOTAL`ブロック、65部門の明示選択、スペクトル半径 |
| WIOD | 国別SUT | `SUTSystem` | 64商品×64産業、総供給と国内Makeの区別、丸め許容差 |

## 既知の切り出し条件と結果

### 日本・経産省/e-Stat

`external_validation/meti_2020/japan_2020_iot_108_producer_price.xlsx` は、108部門のOutput Tableを含む縦長ファイルです。Row Code、Column Code、Special Classification、価格評価列を確認します。同じコードの重複を含むため、ファイル全体を`Z`へ変換しません。出典資料に基づいて取引表ブロックを別途選び、選択後の配列を`IOSystem`へ渡す境界を確認します。

### 英国

`data_raw/iot2023product.xlsx` の `IOT`、`A`、`Leontief` シートを使います。product-by-productの内生部門ブロックをラベルで照合し、最終需要の集計列を重ねて渡さないようにします。`P3 S1` の集計を除き、個別構成項目を`Y`へ渡したケースでは、参照A/Lとdense・iterative経路を比較します。今回のローカルファイルではA参照は数値比較でき、Leontief参照には欠測・非数値が含まれたため、L参照だけ`FAIL`として局所化されました。表本体の構造・係数・安定性は継続して診断できます。

### 台湾

`data_raw/f110c08e.xlsx` の `F110C08e` シートは、購入者価格の163×163取引表です。単位、行・列コード、注記、合計項目を確認してから対象ブロックを選びます。購入者価格に伴うマージン・税などを別途扱う場合は、資料に基づく符号付き`output_adjustments`として渡し、`PriceBasis.PURCHASER`を記録します。自動的な生産者価格変換は行いません。

### 韓国

`data_raw/2023_Input-Output tables_Producer＇s price_Large-Sized.xlsx` の `Transaction_domestic(producer)`、`Transaction_imported(producer)`、`Transaction(producer)`、`Input coefficients(dom)`、`ProductionInducement` を使います。国内中間取引と輸入投入を混同せず、購入部門別の輸入投入を`input_adjustments`として明示します。A/L参照は同じ部門順、価格評価、単位で構成されたものだけ比較します。

### 米国

`data_raw/Table.xlsx` と `data_raw/Table.csv` は同一の15部門total-requirements matrixとして照合します。これは中間取引行列`Z`ではないため、取引表として会計監査へ渡さず、ファイル診断と`L_reference`等の参照検証に使います。BEA/BLSのMake/UseはSUT形式として扱い、v0.1の`IOSystem`へ自動変換しません。

### OECD

`external_validation/oecd_icio_2025/oecd_sut_useva_2020.csv` はSDMX長形式です。`P1`（output）、`P2`（intermediate consumption）、`B1G`（gross value added）などの取引項目、地域、活動、単位、評価を選び、product×industryのブロックを明示的に整形します。長形式からの自動抽出は行いません。

### Eurostat

`external_validation/eurostat_figaro_2026/naio_10_cp1750_EU27_2022.json` から、定義を確認した65部門の`DOM`または`TOTAL`ブロックと`P1`産出を選びます。確認済みのスペクトル半径は`TOTAL=0.572781`、`DOM=0.489554`です。データセット全体を自動分類した結果ではありません。

### WIOD

`external_validation/wiod_2016/JPN_SUT_nov16.xlsx` のSUP/USEから64商品×64産業のUse、最終需要、付加価値、産業産出を選び、`SUTSystem`へ渡します。`SUP_bas`は輸入を含む総供給なので、国内Makeの行和との比較は`output_by_product_scope="total_supply"`としてスキップします。商品側の約112.91 million USDの差は、検証時に明示した`absolute=200.0`、`rounding_unit=200.0`の範囲で評価します。この許容差はライブラリの既定値ではありません。

## 境界

この記録は、抽出コードや国別アダプターの配布を意味しません。`ioaudit`へ渡す直前のデータ整形と意味の確認は利用者が担当します。rawファイルを自動取得、削除、修正、再配布する処理は行いません。
