# AGENTS.md — udi-custom-trac

本書はフォークしたtracについてのAIコーディング共通規則。既存仕様・互換性・利用者の変更を守り、根拠のある最小修正を行う。詳細は対象コードの既存実装を正とする。

## 作業原則

- 開始前に「何をするか」を1行で述べる。3工程以上・複数モジュール・設計判断を伴う作業はPlan Mode（なければ簡潔な計画）を使い、検証まで計画する。
- 修正前に命名・依存・呼出元/先・例外処理・類似実装を調査する。存在しないAPIや仕様を推測して実装しない。
- 不具合は再現条件・原因・影響範囲を特定し、根本原因を修正する。場当たり的な回避策、無関係なリファクタリング、大規模整形、依存更新は行わない。
- 既存の振る舞い・公開API・保存データ・ログ・UIを維持する。仕様に影響する不明点は質問するが、既存コードから判断できる軽微な事項では停止しない。
- エラー処理・後始末・異常系まで実装する。期待されるエラーの扱いが判断できなければ質問する。例外の握りつぶしや根拠のない成功扱いは禁止。
- 実装方針が破綻したら修正を積み重ねず、原因を再調査して計画を改める。タスク範囲外の問題は報告し、無断で修正しない。

## プロジェクト構成

- 本体は `trac/`（`ticket/`、`wiki/`、`web/`、`versioncontrol/` など）。オプションのコンポーネントと Git・Subversion バックエンドは `tracopt/`。
- 共通 Jinja2 テンプレートは `trac/templates/`、機能別テンプレートは各機能の `templates/`。静的ファイルは `trac/htdocs/`、翻訳は `trac/locale/`、同梱 Wiki ページは `trac/wiki/default-pages/`。
- 共通テストは `trac/tests/`、機能別テストは各パッケージの `tests/`。テスト資料は `doc/dev/`、サンプルプラグインは `sample-plugins/`、保守用スクリプトは `contrib/`。

## ビルド・テスト・ローカル開発

- 仮想環境を有効にし、`python -m pip install -e .` で編集可能インストールを行う。
- `trac-admin /path/to/test-env initenv` で開発用環境を作成し、`make server env=/path/to/test-env port=8000` でローカルサーバーを起動する。
- 単体テストは `make unit-test`、ブラウザテストは `make functional-test`、両方は `make test`。個別実行の例は `make test=trac/ticket/tests/model.py`。
- リリース時は `.github/release.sh` に従い、`requirements-release.txt` の依存関係と `setuptools-git` をインストールする。`make compile sdist wheel` で翻訳をコンパイルし、ソースアーカイブと wheel を作成する。

## コーディングスタイルと命名規則

Python はスペース4個で字下げし、関数名・変数名は `snake_case`、クラス名は `CapWords` とする。JavaScript とテンプレートの字下げは周囲に合わせる。Python のチェックは Pylint を導入して `make pylint module=trac.ticket`、テンプレートのチェックは `make jinja` を使う。

## テストの書き方

`unittest.TestCase` に `test_*` メソッドを追加し、新規テストケースは該当する `test_suite()` に登録する。Trac 環境が必要な単体テストでは `trac.test.EnvironmentStub` を使う。`trac/tests/functional/` のブラウザテストは Selenium と Firefox を使う。CI のテスト依存関係は `.github/requirements.txt` を参照する。`make coverage START=` で単体テストの分岐カバレッジレポートを生成する。

## コミット

Forked Repository のため、元の最終開発版`1.7.1`を引きつぎ`1.8.0-dev` から開発を再開するものとする。

GitHub側でISSUE（Branch）を切っていてそれについての作業あれば、ブランチにコミットをする。特に指定がなければmainに直接コミットプッシュを許可する。

## 完了報告（必須）

- `Status: COMPLETE / PARTIAL / BLOCKED`
- `Summary:` 原因、実装内容、維持した互換性
- `Changed Files:` **タスク全体**の対象を `A`（追加）/`M`（変更）/`D`（削除）+ 相対パスで列挙。0件なら`None`。
- `Verification:` 実施項目と結果（PASS/FAIL/NOT RUN/BLOCKED）、ビルド・テストは人間実施で未実行と明記。
- `Risks / Human Verification:` 残課題、手動確認項目、必要なビルド/テスト手順。
