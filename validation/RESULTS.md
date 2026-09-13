# Cross-table validation results

最終確認日: 2026-09-13  
対象ブランチ: `main`  
対象バージョン: `0.2.0.dev0`（検証時点の開発版）
対象コミットは固定せず、更新履歴で確認する。
Python: 3.13.3（ローカル実行）

このファイルは、rawデータそのものではなく、実データを用いた検証結果と解釈を記録します。国別の抽出処理や単位変換をライブラリへ追加したことを意味しません。各データの所在と抽出条件は [`manifest.json`](manifest.json) と [`README.md`](README.md) に記載しています。

## 検証結果

| 対象 | 入力モデル・段階 | 結果 | 解釈 |
| --- | --- | --- | --- |
| 日本・e-Stat API | 抽出前の長形式応答 | 確認済み | 成功応答（manifest記録: `STATUS=0`）、480観測。正方`Z`への自動変換は行わず、呼び出し側のreshapeが必要 |
| 東京都2015 | 抽出前の旧`.xls` | 確認済み | 123×141シートから107部門候補を確認。合計・付加価値・最終需要を含むため、シート全体は`Z`として不適格 |
| 英国 | `IOSystem`、dense / iterative | 検証成功 | Structure・安定性はPASS。会計残差は機械精度レベル。部分subtotal`P3 S1`を検出。欠測を含むLeontief参照は局所FAIL |
| 台湾2023 | `IOSystem`、購入者価格163部門 | 部分確認 | Structure・産出側はPASS。投入側は選択した`V`等で閉じず、最大絶対残差3,503,658。購入者価格の調整項目を明示しないまま投入側を断定できないことを確認 |
| 韓国2023 | `IOSystem`、dense / iterative | 検証成功 | 国内表・輸入投入を分けて扱い、denseでA/L参照を比較。iterativeではLeontief逆行列を生成しない経路をSKIPPEDとして処理 |
| 米国 | `Table.csv` / `Table.xlsx` | ファイル・参照確認 | 15×15のtotal-requirements matrixは両形式で一致。これは取引表`Z`ではないため、`L_reference`等の参照用途として扱う |
| 米国BEA | 抽出前の固定幅Make/Use | 確認済み | Make・Use・Direct Requirementsの固定幅構造、価格評価、丸め注記を確認。自動的なSIOT化は行わない |
| 米国BLS | `SUTSystem` | 検証成功 | 176部門のUse/Makeを明示抽出。商品側・産業側・Makeの会計が指定した丸め許容差内でPASS |
| OECD ICIO 2025 | 抽出前のSDMX長形式Use/VA | 確認済み | 34,248行、活動118、単位XDC、評価・価格基準を確認。長形式から正方SUTを自動推定しない |
| Eurostat FIGARO 2022 | `IOSystem` | 検証成功 | 65部門ブロックを明示選択。`TOTAL`のrho=0.572781、`DOM`のrho=0.489554。全データの自動分類結果ではない |
| WIOD Japan 2014 | `SUTSystem` | 検証成功 | 64商品×64産業。産業側会計は機械精度、商品側は指定した絶対・丸め許容差200 million USD内。国内Makeと総供給の範囲差はSKIPPED |

## 個別ログ

### 日本・e-Stat API

`external_validation/estat_api/0004047205.json`を確認しました。応答は成功としてマニフェストに記録され、480観測の長形式データでした。カテゴリ軸、単位100万円、`-`欠測トークンを確認し、正方行列を推測せず、IOSystem投入前に呼び出し側で表の範囲を決める設計を確認しました。

### 東京都

`prefecture_2015_confirmed_candidates`の東京都旧`.xls`候補を確認しました。シート全体は123×141で、107部門候補のほか合計・付加価値・最終需要に相当する行列が含まれます。107×107の候補を確認しつつ、`x`や`Y`の自動抽出は行いませんでした。空行や合計列を含む公表Excelをそのまま正方`Z`と解釈しないことを確認するケースです。

### 英国・韓国

`docs/local_crosscountry_check.py`を実行し、英国と韓国についてdense/iterativeの両経路を比較しました。英国では`P3 S1`が`P3 S13`〜`P3 S15`の部分subtotal候補として検出され、Leontief参照の欠測は表本体の診断を停止させず、参照診断へ局所化されました。韓国では国内・輸入ブロックを明示的に分け、A/L参照との数値差を確認しました。

### 台湾

`f110c08e.xlsx`の購入者価格163×163ブロックを明示選択しました。産出側は一致しましたが、投入側は選択した付加価値等だけでは恒等式が閉じませんでした。この結果は台湾固有の分岐を追加する根拠ではなく、価格評価や調整項目を利用者が資料に基づいて宣言する必要があることを示します。

### OECD・Eurostat・WIOD

OECDは長形式のUse/Value addedデータであり、product×industryの正方ブロックを自動抽出していません。Eurostatは`ind_ava`、`ind_use`、`DOM`/`TOTAL`を確認したうえで、65部門ブロックを明示して監査しました。WIODは2014年の64商品×64産業SUTへ明示的に整形し、総供給と国内Makeの違いを`output_by_product_scope`で区別しました。

## 実行コマンド

実データのローカル再確認:

```text
python docs\local_crosscountry_check.py
```

パッケージ検証:

```text
python -m pytest -q
python -m compileall -q src tests validation
python -m json.tool validation\manifest.json
python -m twine check <wheel> <sdist>
```

## 解釈上の注意

- `PASS`は、明示された構造・会計式・許容差に対する結果です。公式統計の意味を自動判定したことを示しません。
- `AVAILABLE`は数値を計算できたことを示します。利用者が許容差や分析目的を決める前の値を含みます。
- `SKIPPED`は入力不足、意味の不明、範囲不一致などにより、推測を避けて計算を止めた結果です。
- 購入者価格、輸入・移入、税、マージン、単位、丸め幅は、出典資料に合わせて利用者が指定します。
- rawデータはGit管理・配布物・PyPIへ含めません。
