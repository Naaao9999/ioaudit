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

### v0.1 API freeze

v0.1公開後は、次の公開入口と入力項目の意味を維持します。

- `IOSystem`、`TradeFlows`、`AccountingConvention`、`AuditReport`、`audit()`
- `Z`、`x`、`sectors` の基本位置引数
- `Y`、`V`、`trade`、`input_adjustments`、`output_adjustments`、参照行列、metadata、accountingのkeyword引数
- `PASS`、`AVAILABLE`、`WARNING`、`FAIL`、`SKIPPED` のstatus契約
- 不明な意味を推測せず、影響する診断を `SKIPPED` とする方針

公開後の変更は、原則としてバグ修正、ドキュメント、テスト、内部実装の改善に限定します。新しい表構造は既存の `IOSystem` に無理に追加せず、別モデルとして検討します。

## 次のアップデート候補

### v0.2：意味情報と識別子の明示化

優先候補は、既存のSIOTモデルを維持したまま、表の意味をより機械可読にする機能です。

- `price_basis` の構造化（`producer`、`purchaser`、`basic`、`unknown` など）
- ブロックごとの単位、通貨、価格年、為替・PPP基準の記録
- 国・部門の複合識別子、`region` × `sector` のラベル整合性
- 部門コード、分類体系、crosswalkの整合性診断
- CO2、雇用、エネルギーなどのsatellite accountの形状・ラベル・単位・欠損診断

これらは宣言と検証を目的とし、自動換算、自動マッチング、自動分類は行いません。

### v0.3以降：別データモデル

データ構造がSIOTと異なるものは、`IOSystem` の引数を増やして対応しません。

- MRIO：国×部門に展開済みの `Z` をまず監査し、将来、地域ブロック・二国間フローを専用モデルで扱う
- SUT：`SUTSystem` などの別モデルで Supply、Use、commodity×industry を扱う
- MRIO / SUTの変換、価格評価の変換、交易推計、行列バランシングは別レイヤーの責務とする

## 実データによる検証方針

日本、英国、台湾、韓国、米国、OECD、Eurostat系の公表表を回帰検証に使います。検証の目的は国別処理を増やすことではなく、同じ `IOSystem` → `audit()` API が異なる表現で成立することを確認することです。

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

### v0.1 API freeze

After the v0.1 release, the following public contract is kept stable:

- `IOSystem`, `TradeFlows`, `AccountingConvention`, `AuditReport`, and `audit()`
- the positional meaning of `Z`, `x`, and `sectors`
- the keyword inputs `Y`, `V`, `trade`, `input_adjustments`, `output_adjustments`, references, metadata, and accounting
- the status contract `PASS`, `AVAILABLE`, `WARNING`, `FAIL`, and `SKIPPED`
- the rule that unknown meaning is not inferred and affected diagnostics are `SKIPPED`

After publication, changes are normally limited to bug fixes, documentation, tests, and internal implementation improvements. New table structures should be evaluated as separate models rather than added as ad hoc `IOSystem` arguments.

## Planned updates

### v0.2: explicit semantics and identifiers

The first candidates add machine-readable meaning while keeping the existing SIOT model:

- structured `price_basis` values such as `producer`, `purchaser`, `basic`, and `unknown`
- block-level units, currencies, price years, and exchange-rate or PPP bases
- compound country-sector identifiers and `region` × `sector` alignment
- validation of sector codes, classification systems, and crosswalks
- shape, label, unit, and missing-value diagnostics for satellite accounts such as CO2, employment, and energy

These additions declare and validate meaning. They do not perform automatic conversion, matching, or classification.

### v0.3 and later: separate data models

Data structures that differ from SIOT will not be forced into more `IOSystem` arguments.

- MRIO: first audit an expanded country-by-sector `Z`; later handle regional blocks and bilateral flows in a dedicated model
- SUT: use a separate model such as `SUTSystem` for Supply, Use, and commodity-by-industry tables
- MRIO/SUT transformation, price-basis conversion, trade estimation, and matrix balancing belong in separate layers

## Cross-table validation

Published tables from Japan, the United Kingdom, Taiwan, Korea, the United States, OECD, and Eurostat are used as regression inputs. The purpose is to verify that the same `IOSystem` → `audit()` API works across representations, not to add country-specific code paths.

## Boundaries to preserve

- `diagnose, do not repair`
- unknown accounting meaning is reported as `SKIPPED`
- structurally different table types use separate models
- data acquisition, automatic Excel extraction, automatic sector matching, and automatic unit conversion remain outside the core package
