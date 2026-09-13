# ioaudit roadmap

この文書は、`ioaudit` の現在の対象範囲と、将来の拡張を記録します。国別のExcel形式や統計機関ごとの例外を、現行の `IOSystem` に順次追加する方針ではありません。

## 現行 v0.1

v0.1 の対象は、単一の対称産業連関表（SIOT）を分析コードへ渡す前の監査です。部門の種類が industry か product かは、利用者が `metadata` で明示できます。

実装済みの主な範囲：

- `Z`、`x`、`Y`、`V` の構造、数値、部門ラベル、並び順
- `Y` と `V` の小計・合計項目による二重計上候補
- `TradeFlows` による国際・地域間の交易表現
- `input_adjustments` による投入側の明示的な調整
- `output_adjustments` による購入者価格表などの産出側調整
- 生産者価格・購入者価格などの意味を `metadata["price_basis"]` に記録
- dense / iterative の係数・Leontief系診断
- 参照行列、桁違い候補、符号、ゼロ構造、ファイル形式の診断

`output_adjustments` は、マージン、税、輸入調整などを利用者が資料に基づいて符号付きで用意するための入力です。v0.1 は生産者価格への変換、項目の自動推定、単位換算を行いません。

`TradeFlows` と2次元の `output_adjustments` を併用する場合は、調整項目ごとの役割を `output_adjustment_roles` で明示します。`inflow`、`outflow` は交易との重複を避けるため併用せず、`other` の項目だけを交易と組み合わせます。役割のないブロックは、列名から交易項目かどうかを推測せず、産出側会計を `SKIPPED` とします。

### v0.1 API freeze

v0.1公開後は、次の公開入口と入力項目の意味を維持します。

- `IOSystem`、`TradeFlows`、`AccountingConvention`、`AuditReport`、`audit()`
- `Z`、`x`、`sectors` の基本位置引数
- `Y`、`V`、`trade`、`input_adjustments`、`output_adjustments`、`output_adjustment_roles`、参照行列、metadata、accountingのkeyword引数
- `PASS`、`AVAILABLE`、`WARNING`、`FAIL`、`SKIPPED` のstatus契約
- 不明な意味を推測せず、影響する診断を `SKIPPED` とする方針

公開後の変更は、原則としてバグ修正、ドキュメント、テスト、内部実装の改善に限定します。新しい表構造は既存の `IOSystem` に無理に追加せず、別モデルとして検討します。

## 次のアップデート候補

### v0.2：意味情報・識別子・別データモデル（開発中）

#### 現在の開発ツリーで実装済み

- `PriceBasis` による `producer`、`purchaser`、`basic`、`unknown` の型付き宣言と検証
- `SUTSystem` / `audit_sut()` によるSupply、Use、commodity×industry、Make、付加価値、最終需要の軸と会計整合性の監査
- `output_by_product_scope` による国内生産と総供給の区別
- `MRIOSystem` / `audit_mrio()` による国×部門へ展開済みの `Z`、tuple/MultiIndexラベル、地域ブロック、埋め込み交易の合計会計の監査
- MRIOの不正なY/VをcoreのZ/x診断から分離し、影響する会計側だけを `SKIPPED` とする処理
- sparseなMRIOを含む係数・Leontief系の計算経路
- SUT/MRIO専用のシリアライズ、summary、CI gate

#### v0.2契約（現在の開発ツリーで固定）

- バージョンは公開前開発版として `0.2.0.dev0` とする
- SUT/MRIOの入力軸、`output_by_product_scope`、tuple/MultiIndexラベルの意味を維持する
- 診断statusは `PASS`、`AVAILABLE`、`WARNING`、`FAIL`、`SKIPPED` を使用する
- `passed()` と `raise_for_status()` は同じgate規則を使い、`require_complete` と閾値を明示的に扱う
- coreの構造異常とoptional/supporting inputの異常を分離する
- 不正な入力は推測や自動修正をせず、必要な診断を `SKIPPED` または明示的な `FAIL` とする

#### v0.2リリース前に残す作業

- 開発用CIでAPI契約、実データ検証手順、配布物検査を継続確認する
- `price_basis` と参照行列の評価基準・単位が一致しているかを利用者が確認する手順を検証する
- rawデータを配布物へ含めず、wheel・sdist・クリーン環境インストールを公開前に確認する
- 公開用リポジトリへの反映、リリースタグ作成、PyPI公開は別途承認後に実施する
- `output_adjustments` 単独で交易表現を宣言できる会計モードを検討する
- SUTのSupply表に対応する固有の会計恒等式を追加するか検討する
- `output_adjustments` をscale診断の候補に含めるか検討する

#### 公開前チェックの現在状況

- 340テスト、`compileall`、wheel・sdist作成、`twine check`、クリーン出力先での配布物検査を完了
- 英国、韓国、米国のローカル実データ検証をdense・iterative経路で再実行
- 日本のe-Stat API、東京都旧`.xls`、米国BEA固定幅Benchmark、米国BLS SUTを追加収集して検証。e-Statは480観測の長形式、東京都は107部門候補、BEAは固定幅、BLSは末尾の付加価値行・最終需要列とMakeの向きを確認
- 日本、台湾、OECD、Eurostat、WIODは、rawファイルの所在・抽出条件・検証結果をマニフェストと [`validation/RESULTS.md`](validation/RESULTS.md) に記録済み
- `price_basis`、単位、部門順序、国内/総取引範囲と参照行列の一致確認手順を [`validation/README.md`](validation/README.md) に記録済み
- Python 3.14を含むCI workflowを確認済み。`c2f54cf`のGitHub Actions Run 8は3.10〜3.14と配布物検査を成功。GitHub画面にはcheckoutの非ブロッキング注記とNode 20移行警告が表示されたため、action更新は継続課題
- cleanなwheel・sdistを作成し、`twine check`、依存関係を入れた新規venvへのインストール、最小監査の実行を確認済み
- 公開用リポジトリへの反映、タグ作成、PyPI公開は未実施

これらは宣言と検証を目的とし、自動換算、自動マッチング、自動分類は行いません。MRIO / SUTの変換、価格評価の変換、交易推計、行列バランシングは別レイヤーの責務とします。

v0.2でも、SUT・MRIOの入力切り出しや国別ファイルの自動解析は行いません。利用者が公式資料を確認して、明示した軸のブロックを各モデルへ渡します。

### v0.3以降：意味情報と周辺データ

- ブロックごとの単位、通貨、価格年、為替・PPP基準
- 部門コード、分類体系、crosswalkの整合性診断
- CO2、雇用、エネルギーなどのsatellite accountの形状・ラベル・単位・欠損診断
- MRIOの二国間フローやSUT・MRIO変換を専用レイヤーで扱う

## 実データによる検証方針

日本、英国、台湾、韓国、米国、OECD、Eurostat、WIOD系の公表表を検証対象とします。SUTは `SUTSystem`、国×部門へ展開済みの表は `MRIOSystem`、単一SIOTは `IOSystem` へ明示的に切り出して監査します。検証の目的は国別処理を増やすことではなく、表形式に応じた同じ診断原則が成立することを確認することです。具体的なファイル対応、抽出範囲、許容差、実行手順は [`validation/README.md`](validation/README.md) に記録します。

## 維持する境界

次の原則は将来の拡張でも維持します。

- `diagnose, do not repair`
- 不明な会計意味は推測せず `SKIPPED`
- 構造が異なる表形式は別モデル
- 公式表の取得、Excel自動抽出、部門自動マッチング、単位自動変換は本体の責務にしない

---

# ioaudit roadmap

This document records the current scope and planned expansion. Country-specific spreadsheet layouts and statistical-agency exceptions will not be accumulated in the current `IOSystem` as ad hoc branches.

## Current v0.1

Version 0.1 audits a single symmetric input-output table (SIOT) before it is passed to analytical code. Whether the symmetric dimension represents industries or products can be declared in `metadata`.

The current scope includes:

- structure, numeric values, labels, and ordering for `Z`, `x`, `Y`, and `V`
- possible double counting from subtotal or total components in `Y` and `V`
- international and interregional trade through `TradeFlows`
- explicit input-side adjustments through `input_adjustments`
- purchaser-price-style row-side adjustments through `output_adjustments`
- recording producer/purchaser price meaning in `metadata["price_basis"]`
- dense and iterative coefficient and Leontief diagnostics
- reference matrices, scale-error evidence, signs, zero structure, and file diagnostics

`output_adjustments` lets the caller supply signed margins, taxes, import adjustments, or similar terms after checking the source documentation. v0.1 does not convert to producer prices, infer components, or convert units.

When a two-dimensional `output_adjustments` block is used together with `TradeFlows`, every component role must be declared through `output_adjustment_roles`. `inflow` and `outflow` are rejected as overlapping trade inputs; only components marked `other` may be combined with `TradeFlows`. Without roles, the output-side identity is skipped rather than inferred from labels.

### v0.1 API freeze

After the v0.1 release, the following public contract is kept stable:

- `IOSystem`, `TradeFlows`, `AccountingConvention`, `AuditReport`, and `audit()`
- the positional meaning of `Z`, `x`, and `sectors`
- the keyword inputs `Y`, `V`, `trade`, `input_adjustments`, `output_adjustments`, `output_adjustment_roles`, references, metadata, and accounting
- the status contract `PASS`, `AVAILABLE`, `WARNING`, `FAIL`, and `SKIPPED`
- the rule that unknown meaning is not inferred and affected diagnostics are `SKIPPED`

After publication, changes are normally limited to bug fixes, documentation, tests, and internal implementation improvements. New table structures should be evaluated as separate models rather than added as ad hoc `IOSystem` arguments.

## Planned updates

### v0.2: semantics, identifiers, and separate models (in development)

#### Implemented in the current development tree

- typed and validated `PriceBasis` values: `producer`, `purchaser`, `basic`, and `unknown`
- compound country-sector identifiers and `region` × `sector` alignment
- `SUTSystem` / `audit_sut()` for Supply, Use, commodity-by-industry, Make, value added, final demand, and their accounting identities
- explicit `output_by_product_scope` handling for domestic output versus total supply
- `MRIOSystem` / `audit_mrio()` for an already expanded country-by-sector `Z`, tuple/MultiIndex labels, regional blocks, and embedded-flow totals
- separation of malformed MRIO supporting Y/V inputs from core Z/x diagnostics
- sparse MRIO coefficient and Leontief calculation routes
- serializable SUT/MRIO reports with summaries and CI gates

#### v0.2 contract (fixed in the current development tree)

- the version is `0.2.0.dev0` until a public release is approved
- SUT/MRIO input axes, `output_by_product_scope`, and tuple/MultiIndex label semantics remain stable
- diagnostic statuses use `PASS`, `AVAILABLE`, `WARNING`, `FAIL`, and `SKIPPED`
- `passed()` and `raise_for_status()` share the same gate rules, with explicit completeness and threshold controls
- core structural errors are separated from optional/supporting input errors
- invalid meaning is never inferred or repaired; affected checks are `SKIPPED` or explicitly `FAIL`

#### Remaining before the v0.2 release

- keep API-contract, real-data runbook, and distribution checks green in development CI
- verify the documented procedure for checking that reference matrices use the same valuation and units as the audited table
- keep raw validation data out of distributions and verify wheel, sdist, and clean-environment installation
- reflect the approved release in the public repository, create a release tag, and publish to PyPI only after separate approval

#### Current pre-publication status

- 340 tests, `compileall`, wheel/sdist creation, `twine check`, and distribution inspection in a clean output directory are complete
- UK, Korea, and US local-data checks were rerun through the dense and iterative routes
- Japan, Taiwan, OECD, Eurostat, and WIOD raw-file locations, extraction conditions, and validation results are recorded in the manifest and [`validation/RESULTS.md`](validation/RESULTS.md)
- A procedure for checking `price_basis`, units, sector order, domestic/total scope, and reference-matrix compatibility is recorded in [`validation/README.md`](validation/README.md)
- The CI workflow including Python 3.14 has been verified. GitHub Actions Run 8 for `c2f54cf` succeeded on Python 3.10–3.14 and distribution checks; non-blocking checkout and Node 20 migration annotations remain follow-up items
- A clean wheel and sdist passed `twine check`, fresh-venv installation, and a minimal audit smoke test
- Public-repository promotion, tagging, and PyPI publication have not been performed
- consider an explicit output-accounting mode for `output_adjustments` without a trade representation
- consider dedicated Supply identities for SUT audits
- consider including `output_adjustments` in scale-diagnostic candidates

These additions declare and validate meaning. They do not perform automatic conversion, matching, or classification. MRIO/SUT transformation, price-basis conversion, trade estimation, and matrix balancing belong in separate layers.

The v0.2 implementation does not parse country-specific files or extract blocks automatically. The caller is responsible for selecting and documenting the axes before constructing either model.

### v0.3 and later: semantic context and auxiliary data

- block-level units, currencies, price years, and exchange-rate or PPP bases
- validation of sector codes, classification systems, and crosswalks
- shape, label, unit, and missing-value diagnostics for satellite accounts such as CO2, employment, and energy
- bilateral MRIO flows and SUT/MRIO transformations in dedicated layers

## Cross-table validation

Published tables from Japan, the United Kingdom, Taiwan, Korea, the United States, OECD, Eurostat, and WIOD are validation targets. Single SIOTs use `IOSystem`, SUTs use `SUTSystem`, and already expanded country-by-sector matrices use `MRIOSystem`. The purpose is to verify the same diagnostic principles across table representations, not to add country-specific code paths. File mappings, extraction ranges, tolerances, and commands are recorded in [`validation/README.md`](validation/README.md).

## Boundaries to preserve

- `diagnose, do not repair`
- unknown accounting meaning is reported as `SKIPPED`
- structurally different table types use separate models
- data acquisition, automatic Excel extraction, automatic sector matching, and automatic unit conversion remain outside the core package
