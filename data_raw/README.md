# Local validation data

このディレクトリは、ioaudit の手元での実データ検証用です。

ここに置くファイルは Git 管理対象外です。元ファイルを移動せず、検証時の誤削除を避けるためにコピーを保存します。

主な内容

- 日本の e-Stat 関連ファイル
- 英国、韓国、米国、台湾の検証用ファイル
- 都道府県間産業連関表の確認済み候補ファイル

米国表については、`Table.xlsx` / `Table.csv` が2024年の15部門の総必要量行列です。`L_reference` とファイル診断の検証に使用します。`Z` として利用する中間取引表ではありません。

追加した `us_bea_2002_summarytables.zip` と `us_bea_2002_detail_redef.zip` は、米国BEAが公開する2002年ベンチマークのMake/Use、Direct Requirements、Total Requirements資料です。Make/UseはSUT形式のため、v0.1の`IOSystem`へ自動変換せず、形式境界と参照資料の確認に使用します。

`us_bls_input_output.zip` は、米国BLSの研究者向けデータです。1997–2025年の名目・実質I-Oデータと2035年予測、部門対応表、レイアウト説明を含みます。`USE` は商品×産業の使用表で、末尾の行が付加価値、末尾の列が最終需要です。したがって、見かけ上は正方でも、v0.1の単一SIOTの`Z`へそのまま渡さず、SUT形式の読み違い検出と抽出手順の検証に使用します。

出所: https://www.bea.gov/industry/benchmark-input-output-data
　　　https://www.bls.gov/emp/data/input-output-matrix.htm

原典、利用条件、抽出範囲は各ファイルの出所と付属資料を確認してください。ioaudit は表の範囲や `Z`、`x`、`Y`、`V` を自動確定しません。

## 必須4系統の実データ検証

公開データの表現差を確認するため、次の4系統を実データの検証対象として保存しています。ファイルはGit管理対象外です。CIの通常テストは外部ファイルに依存せず、ここでの結果は手元で再実行する実データ回帰の記録として扱います。

### 日本・経済産業省／e-Stat

- ローカルファイル: `external_validation/meti_2020/japan_2020_iot_108_producer_price.xlsx`
- 形式: 108部門のOutput Table。`Row Code`、`Column Code`、特殊分類、価格評価別の列を持つ縦長形式
- 確認結果: 10,075行、行コード118種類、列コード130種類。特殊分類を含む同一行列コードの重複が674件あるため、ファイル全体をそのまま正方行列へ変換しない
- 利用方法: e-Statの表定義を確認したうえで、分析対象の取引表ブロックを呼び出し側で明示的に切り出す。今回のファイルは、Excelの表範囲・特殊分類・価格列を自動推定しない境界の確認に使う
- 公式情報: <https://www.e-stat.go.jp/en/stat-search/files?cycle=0&layout=datalist&month=0&toukei=00200603&tstat=000001218140&year=20200>
- 経済産業省の関連表: <https://www.meti.go.jp/statistics/tyo/entyoio/result.html>

### WIOD 2016

- ローカルファイル: `external_validation/wiod_2016/JPN_SUT_nov16.xlsx`
- 研究用原データ: `G:/マイドライブ/1大学関連/2026/4.新規研究案/data/wiod/raw/`
- 形式: 日本の国別SUT（2014年、64商品・64産業、SUP/USEシート）と、研究用フォルダにある43か国＋ROWのWIOT
- 確認結果: 国別SUTから `use` 64×64、最終需要、付加価値、産業別産出、供給側の産出を明示抽出して `audit_sut()` を実行した。産業側残差は約1.5×10^-8 million USD、商品側残差は112.91 million USDで、今回の検証用に明示した許容幅の範囲内として記録できた。この許容幅200.0 million USDはライブラリの既定値ではない
- 注意点: `SUP_bas` は輸入を含む総供給であり、国内生産行列 `make` の行和とは意味が異なる。したがって、供給と国内生産を同じベクトルとして比較しない。SUTの軸と評価範囲は利用者が資料に基づいて指定する
- 公式情報: <https://www.rug.nl/ggdc/valuechain/wiod/wiod-2016-release>
- DOI: <https://doi.org/10.34894/PJ2M1C>

### OECD

- ローカルファイル: `external_validation/oecd_icio_2025/oecd_sut_useva_2020.csv`
- 形式: OECD SDMXの長形式データ。2020年のUse、Value addedおよびその構成要素を含み、40地域、118活動、複数の取引項目を持つ
- 確認結果: 34,248行を読み込み、活動、取引項目、評価、単位、通貨、表識別子を確認した。これはそのまま行列ではなく、`P1`、`P2`、`B1G`などの項目を選び、必要な軸を明示してから `SUTSystem` へ渡す形式である
- 利用方法: OECDのSDMX定義に従って表の軸・単位・価格基準を選択する。`ioaudit` は長形式から `Z`、`Y`、`V` を自動抽出しない
- 公式情報: <https://www.oecd.org/en/data/datasets/inter-country-input-output-tables.html>
- API案内: <https://www.oecd.org/en/data/insights/data-explainers/2024/09/api.html>

### EU・Eurostat

- ローカルファイル: `external_validation/eurostat_figaro_2026/naio_10_cp1750_EU27_2022.json`
- 形式: Eurostatの2022年EU27集計、基本価格のindustry-by-industry対称表。国内利用（`DOM`）と合計（`TOTAL`）のフローを含む
- 確認結果: 共通する集計産業コードを呼び出し側で選び、65×65の明示ブロックと `P1` 産出ベクトルを構成した。`TOTAL` のスペクトル半径は0.572781、`DOM` は0.489554で、構造・係数・安定性の監査を完了した。両方とも `report.passed()` は真だった
- 注意点: データセットには合計・詳細分類・会計項目が同じ軸に含まれる。今回の65部門ブロックは定義に基づく明示選択であり、一般のEurostatファイルに対する自動抽出機能ではない
- 公式データベース: <https://ec.europa.eu/eurostat/en/web/esa-supply-use-input-tables/database>
- データセット: <https://ec.europa.eu/eurostat/databrowser/product/page/naio_10_cp1750>

この4系統で確認した共通の境界は、ファイル取得・表範囲の選択・部門コードの対応・価格評価の判断を利用者が担当し、`ioaudit` が明示された配列またはSUT/MRIOブロックの構造、会計関係、数値安定性を監査することです。表の意味が確定できない場合は、値を補わず該当診断を `SKIPPED` とします。
