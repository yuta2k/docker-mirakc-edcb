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
| `EDCBTEST_MIRAKC_IMAGE` | `mirakc:integration-test` | フェーズ 5 でビルドしてテストする mirakc のイメージのタグ。`EDCBTEST_SKIP_BUILD=1` でも、無ければビルドする |
| `EDCBTEST_QSVENCC_VERSION` | (GitHub の最新リリース) | T57 で入れる QSVEncC の版 |
| `EDCBTEST_REAL_INI` | `edcb/ini`(`*.ini` があれば) | T3 と T46 で使う実際の ini のディレクトリ。一時ディレクトリへコピーするだけで、元のファイルは変えない。無ければ T3 は SKIP、T46 は合成したデータを使う |

## ホストで触るもの

- このスクリプトが作った `${EDCBTEST_PREFIX}-*` という名前のコンテナ(終了時に消す)
- このスクリプトが作ったネットワーク `${EDCBTEST_PREFIX}-net`(フェーズ 3 の偽サーバ用。終了時に消す)
- イメージのタグ `$EDCBTEST_IMAGE` と、ビルドが失敗することを確かめる `$EDCBTEST_IMAGE-shouldfail`、ハードウェアエンコードの見本の `$EDCBTEST_IMAGE-hwaccel` と `$EDCBTEST_IMAGE-hwaccel-qsvencc`、mirakc の `$EDCBTEST_MIRAKC_IMAGE`
- フェーズ 6 の Compose のプロジェクト `${EDCBTEST_PREFIX}-p6setup` と `${EDCBTEST_PREFIX}-p6migrate`(コンテナ、ネットワーク、ボリューム)と、v1 を模したコンテナ `${EDCBTEST_PREFIX}-v1-edcb` / `${EDCBTEST_PREFIX}-v1-mirakc`、ボリューム `${EDCBTEST_PREFIX}-v1_mirakc_epg`(終了時に消す)
- `mktemp -d` で作る一時ディレクトリ(終了時に消す)
- `127.0.0.1` のポート `EDCBTEST_PORT_BASE` から 3 つ
- ログファイル

Compose のプロジェクトは、フェーズ 6 の上記のものだけを使う(一時ディレクトリの中で、`${EDCBTEST_PREFIX}-` で始まる名前)。稼働中のコンテナや `edcb/ini/`、`mirakc/config.yml`、`compose.yml` には触らない。`prune` のようなホスト全体に効くコマンドも使わない。

`${EDCBTEST_PREFIX}-*` のコンテナ、ネットワーク、ボリュームが既にあると、消さずに終了する(前回の実行が残ったものなら手で消すか、`EDCBTEST_PREFIX` を変える)。

ホストに `/dev/dri/renderD*` が無いときは、T6 のうち render グループの確認だけを飛ばす(`--group-add` の確認は行う)。

## ファイル

- `run.sh` — 入口。設定と前提の確認、後片付け、集計
- `lib.sh` — 共通の関数(`result`、`section`、`run`、`wait_log`、`wait_health` など)
- `phase2.sh` — フェーズ 2 の確認(T0〜T15)。内容は `docs/v2/phases/2-provision.md` の「検証結果」
- `phase3.sh` — フェーズ 3 の確認(T30〜T39)。偽の Mirakurun(`edcb/tests/fake_mirakurun.py`)を、テストするイメージの python3 でテスト用ネットワークに立て、ホスト名でつなぐ。T35 は到達できない接続先として `192.0.2.1`(文書用のアドレス)を使う
- `phase4.sh` — フェーズ 4 の確認(T40〜T49)。`phase3.sh` のネットワークと `fake` を使う。偽の Mirakurun は空のパケットしか送らず、本物の `EpgDataCap_Bon` ではサービスが見つからないので、スキャンは偽の `EpgDataCap_Bon`(`edcb/tests/fake_epgdatacap.py`。環境変数 `EDCB_PROVISION_EPGDATACAP` で差し替える)で行う。T47 だけ本物の `EpgDataCap_Bon` で、全チャンネルを選局すること、何も見つからないときにファイルを変えないことを確かめる。T46 は `EDCBTEST_REAL_INI` の `Setting/` に ChSet4 と ChSet5 があれば、それを一時ディレクトリにコピーして使う(無ければ合成したデータ)
- `phase5.sh` — フェーズ 5 の確認(T50〜T58)。mirakc のイメージをビルドし、`mirakc/config-sample.yml` で起動して、内蔵の pcscd の起動・停止の切り替え(ダミーのソケットをマウント、`DISABLE_PCSCD=1`)、`docker stop` の速さ、`docker restart` 後の再起動を確かめる(チューナーとカードリーダーは要らない)。T56 は mirakc を無効にした `compose.override.yml` で `docker compose config` を確かめる。T57 はハードウェアエンコードの見本を、テストするイメージの上にビルドする(amd64 のみ。GPU は要らない。GitHub の API で QSVEncC の最新版を調べる)。T58 は `phase3.sh` のネットワークと `fake`、`phase4.sh` の `FAKESCAN` を使い、接続先を外したときの起動時の警告と `edcbctl prune` を確かめる
- `phase6.sh` — フェーズ 6 の確認(T60、T61)。`Setup.md` の手順(T60)と `docs/migration-v1-to-v2.md` の手順(T61)を、文書の順に Compose で実行する。リポジトリで管理しているファイルを作業ツリーから一時ディレクトリへコピーして使う(コミットしていない変更も確かめる)。イメージは Compose でビルドせず、T0 と T50 のイメージを `compose.test.yml`(`.env` の `COMPOSE_FILE` で重ねる)で指定する。T61 は、v1 と v2 の 2 つのコミットを持つ一時的な git リポジトリで `git pull` の動き(未追跡の `compose.yml` で止まること)を確かめ、v1 のコンテナは `sleep` で代用する。`docker compose` か `git` が無ければ SKIP
- `fixtures/` — 確認で使うファイル。`v1-compose-sample.yml` は v1.0.4 の `compose-sample.yml`(T61 で v1 の構成を作る元)

## 確認を足す

- 新しいフェーズは `phaseN.sh` を作る。`run.sh` が `phase*.sh` をすべて番号順に読み込む。
- 偽の Mirakurun が要る確認は、`phase3.sh` の `fake` を使う(`fake <コンテナ名> <ホスト名> <シナリオ>`)。シナリオは `edcb/tests/fake_mirakurun.py` の `SCENARIOS`。
- コンテナ名は `cname <番号>` で作り、`run <名前> <ディレクトリ> [docker run のオプション...]` で起動する(後片付けの対象に入る)。`docker run` を直接使うときは、先に `track <名前>` を呼ぶ。
- データは `$TMP` の下に作る。ホストのポートは `$PORT_HTTP` などの変数を使い、番号を書かない。足りなければ `run.sh` に変数を足す。
- 結果は `result <id> "PASS ..."` / `"FAIL ..."` / `"SKIP 理由"` で出す。ホストに無い機能に依存する確認は、FAIL ではなく SKIP にする。
