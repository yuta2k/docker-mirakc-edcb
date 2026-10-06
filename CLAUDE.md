# docker-mirakc-edcb

Linux 版 EDCB (EpgTimerSrv / EpgDataCap_Bon) を BonDriver_LinuxMirakc 経由で mirakc / Mirakurun につなぐ Docker Compose 構成。

## 構成

- `compose.yml` — 全員共通の定義。利用者ごとの差分は `compose.override.yml`、`edcb.env`、`.env`(どれも git 管理外)
- `edcb/Dockerfile` — 上流のバージョンは `ARG` の既定値が唯一の定義場所。パッチは `edcb/patches/{edcb,bondriver}/`
- `edcb/rootfs/` — entrypoint と、起動時の設定処理(`usr/local/lib/edcb-provision/`、Python 標準ライブラリのみ)、`edcbctl`
- `edcb/tests/` — pytest と偽の Mirakurun / EpgDataCap_Bon
- `edcb/hwaccel/intel/` — ハードウェアエンコードの拡張の見本
- `mirakc/` — mirakc イメージ(版とダイジェストで固定)と、pcscd を切り替える entrypoint
- 利用者向けの文書: `Readme.md`、`Setup.md`、`docs/migration-v1-to-v2.md`

## 設計資料

`docs/v2/` に、v2 で作り直したときの方針と調査結果がある。挙動を変える前に読むこと。

- `docs/v2/decisions.md` — ユーザと合意済みの方針(勝手に変えない。変える必要が出たら、実装を進めずユーザに確認する)
- `docs/v2/facts.md` — 上流のソースで確かめた事実(上流は変わるので、使う前に確かめ直す。誤りを見つけたら直す)
- `docs/v2/design.md` — 仕様(環境変数、ファイル配置、起動時の処理)。挙動を変えたら合わせて直す
- `docs/v2/phases/` — 各フェーズの作業記録

## 絶対に守ること

- **`edcb/ini/`、`mirakc/config.yml`、`compose.override.yml`、`edcb.env`、`.env` は利用者の実データ。読むのはよいが、書き換え・削除・移動をしない。** テストは一時ディレクトリで行う。
- **稼働中のコンテナを止めない。** `docker compose up/down/restart` をリポジトリ直下でそのまま実行しない(録画が中断する)。検証は別のディレクトリ、別のプロジェクト名(`-p edcbtest` など)、別のポートで行う。
- 上の 2 つは既定の扱い。ユーザから「壊してよい」「止めてよい」と明示的に伝えられている場合は、その範囲で実データや直下の構成を使ってよい。その場合も、Docker のコマンドはこのリポジトリが作ったものだけを対象にする(ホスト全体に効くコマンドを使わない)。
- **実行していない検証を「通った」と報告しない。** Docker を実行できない環境では、実行するコマンドをまとめてユーザに依頼し、出力を見てから結果を書く。
- **push、PR 作成、タグ作成、GHCR への公開、GitHub 上のリポジトリ作成は、ユーザの明示的な指示があるときだけ行う。**

## 検証

- コミットの前に `scripts/check.sh` を通す(Docker デーモン不要。pytest、shellcheck、actionlint、compose、文書のリンク、環境固有の情報の混入チェック)。
- Docker が要る確認は `tests/integration/run.sh`(root で実行。使い方は `tests/integration/README.md`)。新しい確認はスクラッチに置かず、ここに足す。entrypoint、起動時の設定処理、Dockerfile、compose、文書の手順を変えたら、全項目を実行する。
- コミットするファイルに、特定の環境の情報(ホームディレクトリのパス、ホスト名、プロジェクト名、LAN のアドレス)を書かない。`scripts/git-hooks/` のフックが止める(`git config core.hooksPath scripts/git-hooks`)。
- 文書に書く環境変数、コマンド、ファイル名、出力の例は、実装と突き合わせる。

## 慣例

- ドキュメント(README、Setup、docs/)は日本語。Dockerfile やスクリプト内のコメントは英語。
- コミットメッセージは英語で `feat:` / `fix:` / `docs:` / `ci:` / `refactor:` / `test:` の接頭辞を付ける。
- 上流のソースを調べるときは、リポジトリの外(スクラッチ用の一時ディレクトリ)に clone する。
