# 結合テスト(Docker)

イメージを実際にビルドしてコンテナを起動し、起動時のプロビジョニングや権限の切り替え、ヘルスチェックなどを確かめる。各フェーズで追加した確認を、後のフェーズの回帰確認として繰り返し使う。

## 実行

root で実行する(後片付けで、別の UID が所有するファイルを消すため)。

```sh
sudo tests/integration/run.sh
```

結果は `RESULT <id>: PASS|FAIL|SKIP <詳細>` の行と、最後の `SUMMARY: pass=N fail=N skip=N` で示す。FAIL が 1 つでもあれば終了コードは 1、無ければ 0。root でない、必要なコマンドが無い、などで始められないときは 2。

出力は標準出力とログファイルの両方に出る。ログの所有者は、終了時に `sudo` を実行した利用者(`SUDO_UID:SUDO_GID`)に戻す。`sudo` を使わずに root で実行した場合は、リポジトリのディレクトリの所有者にする。

GitHub Actions では、先にイメージをビルドしてから次のように実行する。

```sh
sudo EDCBTEST_IMAGE=edcb:ci EDCBTEST_SKIP_BUILD=1 tests/integration/run.sh
```

## 環境変数(すべて省略可)

| 変数 | 既定値 | 内容 |
|---|---|---|
| `EDCBTEST_IMAGE` | `edcb:integration-test` | ビルドしてテストするイメージのタグ |
| `EDCBTEST_SKIP_BUILD` | (なし) | `1` ならビルドしない。T0 と T0b は SKIP。イメージが無ければ始めずに終了する |
| `EDCBTEST_PREFIX` | `edcbtest` | コンテナ名の接頭辞 |
| `EDCBTEST_PORT_BASE` | `15510` | ホスト側のポート。この番号から 3 つ(`+0`〜`+2`)を `127.0.0.1` に公開する |
| `EDCBTEST_LOG` | `tests/integration/logs/run-<日時>.log` | ログファイル |
| `EDCBTEST_REAL_INI` | `edcb/ini`(`*.ini` があれば) | T3 で使う実際の ini のディレクトリ。一時ディレクトリへコピーするだけで、元のファイルは変えない。無ければ T3 は SKIP |

## ホストで触るもの

- このスクリプトが作った `${EDCBTEST_PREFIX}-*` という名前のコンテナ(終了時に消す)
- イメージのタグ `$EDCBTEST_IMAGE` と、ビルドが失敗することを確かめる `$EDCBTEST_IMAGE-shouldfail`
- `mktemp -d` で作る一時ディレクトリ(終了時に消す)
- `127.0.0.1` のポート `EDCBTEST_PORT_BASE` から 3 つ
- ログファイル

Compose のプロジェクトは使わない。稼働中のコンテナや `edcb/ini/`、`mirakc/config.yml`、`compose.yml` には触らない。`prune` のようなホスト全体に効くコマンドも使わない。

`${EDCBTEST_PREFIX}-*` のコンテナが既にあると、消さずに終了する(前回の実行が残ったものなら手で消すか、`EDCBTEST_PREFIX` を変える)。

ホストに `/dev/dri/renderD*` が無いときは、T6 のうち render グループの確認だけを飛ばす(`--group-add` の確認は行う)。

## ファイル

- `run.sh` — 入口。設定と前提の確認、後片付け、集計
- `lib.sh` — 共通の関数(`result`、`section`、`run`、`wait_log`、`wait_health` など)
- `phase2.sh` — フェーズ 2 の確認(T0〜T15)。内容は `docs/v2/phases/2-provision.md` の「検証結果」
- `fixtures/` — 確認で使うファイル

## 確認を足す

- 新しいフェーズは `phaseN.sh` を作る。`run.sh` が `phase*.sh` をすべて番号順に読み込む。
- コンテナ名は `cname <番号>` で作り、`run <名前> <ディレクトリ> [docker run のオプション...]` で起動する(後片付けの対象に入る)。`docker run` を直接使うときは、先に `track <名前>` を呼ぶ。
- データは `$TMP` の下に作る。ホストのポートは `$PORT_HTTP` などの変数を使い、番号を書かない。足りなければ `run.sh` に変数を足す。
- 結果は `result <id> "PASS ..."` / `"FAIL ..."` / `"SKIP 理由"` で出す。ホストに無い機能に依存する確認は、FAIL ではなく SKIP にする。
