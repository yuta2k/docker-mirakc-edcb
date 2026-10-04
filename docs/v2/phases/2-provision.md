# フェーズ 2: プロビジョニングの基盤

## 目的

起動時に EDCB の設定を整える仕組みを作る。接続先は従来どおり 1 つ(`MIRAKC_ADDRESS` / `MIRAKC_PORT`)のままで、複数バックエンドとチャンネル定義はこのフェーズでは扱わない。

関連する方針: `decisions.md` の B1〜B3、C2、C3、D1、E1〜E3。仕様: `design.md` の 3.1、4、5、6、10 章。

## 先に確認すること

`facts.md` の U3〜U8 を確認し、結果を `facts.md` に反映する。U3 の結果で `HttpPublic` の置き場所が決まる(`design.md` の 6 章の判断基準)。

## 作業

### 1. プロビジョニングの本体

- `edcb/rootfs/usr/local/lib/edcb-provision/` に Python で実装する。イメージに `python3` を追加する。外部ライブラリは使わない(標準ライブラリのみ)。
- 次の部品に分ける。それぞれ pytest で単体テストを書く。
  - **ini の編集**(`design.md` の 5.2): 行を保ったまま、指定したキーだけを書き換える
  - **設定の収集**: 環境変数と上書き用 ini から「書き込むキーの一覧」を作る。強制するものと、キーが無いときだけ書くものを区別する
  - **適用**: 退避、書き換え、変更内容の表示。`--diff` では表示だけ
  - **状態ファイル**(`design.md` の 5.3)
- `design.md` の 3.1 の表の変数をすべて実装する。3.2(接続先)はフェーズ 3。

### 2. entrypoint

- `design.md` の 5 章の順序に作り直す。
- root で起動し、`setpriv` で `PUID` / `PGID` に落とす。root でないときは、移行方法を示すエラーメッセージを出して終了する。
- `chmod 777` / `chmod 666` を Dockerfile から無くす。
- 接続先の処理は、このフェーズでは現状の動作を保つ(`MIRAKC_ADDRESS` を名前解決して BonDriver の ini に書く)。ただし**名前解決に失敗しても終了しない**。警告を出して起動を続ける。
- デバッグログを標準出力へ流す(`EDCB_LOG_STDOUT`)。

### 3. HttpPublic

`design.md` の 6 章のとおり。U3 の結果に従う。

### 4. そのほか

- Dockerfile に `HEALTHCHECK` を足す(`design.md` の 10 章)。
- `compose.yml` に `env_file`、`overrides` のマウント、追加のポート、`stop_grace_period`(U6 の結果で値を決める)を足す。
- `edcb.env-sample` を作る。
- `edcbctl provision [--diff]` と `edcbctl allow-setting on|off|status` を作る。ほかのサブコマンドはフェーズ 3、4。
- Legacy WebUI の設定変更の許可を、起動中に切り替えられるようにする(`design.md` の 3.3)。`edcb.GetPrivateProfile` に渡せるパスの形(相対パスの基準、絶対パスが使えるか)は、EDCB のソース(Lua API の実装)で確認する。
- `chlegacyset.sh` を削除する(`edcbctl allow-setting` と `EDCB_LEGACY_ALLOW_SETTING` で置き換え)。
- CI の `build.yml` に pytest の実行を足す。

## 触らないもの

- 利用者が WebUI で設定するキー(録画マージン、プリセットなど)。プロビジョニングの対象にしない
- BonDriver のソース(フェーズ 3)

## 受け入れ条件

- [x] 空のディレクトリを `/var/local/edcb` にマウントして起動すると、`design.md` の 3.1 の既定値が書かれた状態で EpgTimerSrv が動く
- [x] 同じ構成で再起動しても、ini が変化しない(変更内容の表示が「変更なし」になる)
- [x] **既存の利用者のデータを模した ini**(現在の `edcb/ini/` の `*.ini` を一時ディレクトリにコピーしたもの)で起動すると、既にあるキーの値は 1 つも変わらない。追加されるのは、無かったキーだけ
- [x] WebUI 相当の変更(ini のキーを手で書き換える)をしてから再起動しても、環境変数と上書き用 ini で指定していないキーは元に戻らない
- [x] 値が `0` や空文字のキー(WebUI でオフにした状態)は「存在する」と扱われ、既定値で上書きされない(`SaveLogo=0`、`[SET_TCP] Count=0`、`EnableTCPSrv=0` で確認)
- [x] 環境変数で指定したキーは、手で書き換えても再起動で戻る
- [x] `edcbctl allow-setting on` の直後から、コンテナを再起動せずに Legacy WebUI の設定ページで保存できる。`off` の直後から保存が拒否される(設定ページへの POST の応答で確認)
- [x] 許可した状態でコンテナを再起動すると、`EDCB_LEGACY_ALLOW_SETTING` の値(未指定なら禁止)に戻る
- [x] `legacy/util.lua` の置き換え対象の行が無い状態を作ると、イメージのビルドが失敗する
- [x] `group_add` で渡したグループと、`/dev/dri/renderD*` の所有グループ(存在する場合)が、権限を落としたあとのプロセスに残る
- [x] 上書き用 ini に書いたキーが反映される。コメントや、ほかのキーの並びは変わらない
- [x] 書き換えの前に退避が作られ、`--diff` では何も書き換わらない
- [x] `PUID=1234 PGID=1234` で起動すると、EpgTimerSrv のプロセスと、新しく作られるファイルの所有者が 1234 になる
- [x] `user: 1000:1000` を付けて起動すると、移行方法を示すメッセージを出して終了する
- [x] 接続先に届かない状態でも、EpgTimerSrv が起動する
- [x] `docker stop` で、EpgTimerSrv と子プロセスが残らずに終了する
- [x] ヘルスチェックが healthy になる。`EnableHttpSrv=0` にしても unhealthy にならない
- [x] pytest がすべて通る

## 検証

フェーズ 1 と同じく、一時ディレクトリと別のコンテナ名・ポートで行う。既存データの確認には、`edcb/ini/` を**コピー**して使う(元は書き換えない)。

```sh
tmp=$(mktemp -d); cp -a edcb/ini/*.ini "$tmp/"   # ini だけコピーする。Setting/ は大きいので必要な分だけ
```

## 実機確認の依頼

- HTTPS: `ssl_cert.pem` を置いて起動し、`https://<ホスト>:5511/E3/` でライブ視聴(TS-Live!)ができるか。手順をまとめてユーザに依頼する。
- (フェーズ 2 で追加)録画中の `docker stop`: チューナーを使って録画している最中に `docker compose stop edcb` を実行し、録画ファイルが閉じられること(再生できること)と、停止までの時間を確かめる。チューナーの無い検証では EpgDataCap_Bon が動かないため、子プロセスの終了は確かめられていない。

### 依頼する手順(未実施)

チューナーがつながった構成で行う。同じホストに別の構成がある場合は、`docker compose config` の `name:` が対象のプロジェクトであることを先に確かめる。v2 のイメージは `user:` を拒否するので、`compose.override.yml` に `user:` があれば消し、`environment` に `PUID` / `PGID` を書く。

```sh
# 証明書(subjectAltName はブラウザでアクセスするアドレスに合わせる)
openssl req -new -newkey rsa:2048 -nodes -keyout /tmp/k.pem -out /tmp/c.pem -x509 -days 3650 -sha256 \
  -subj /CN=edcb -addext "subjectAltName = IP:<ホストの IP>"
cat /tmp/c.pem /tmp/k.pem > edcb/ini/ssl_cert.pem && rm /tmp/k.pem /tmp/c.pem
# EpgTimerSrv.ini の HttpPort を消しておくと、ssl_cert.pem があるときの既定値(5510,5520,5511s,5521s)が書かれる
docker compose up -d --build
docker compose logs edcb | grep -E '(provision|entrypoint):'
```

HTTPS(コンテナ内 5511)と SSE 専用ポート(5520 / 5521)は `compose.yml` では公開していないので、`compose.override.yml` の `ports` に足す(`compose.override-sample.yml` の例。EMWUI は SSE に「ブラウザで開いたポート + 10」を使うので、ホスト側も 10 違いにする)。`ports: !override` を使っている場合は、その中に足す。

1. ブラウザで `https://<ホストの IP>:<コンテナの 5511 に対応するホストのポート>/E3/` を開き、証明書を信頼したうえでライブ視聴(TS-Live!)ができるか。コンテナの 5510(HTTP)に対応するポートを `https://` で開くと、ブラウザは `SSL_ERROR_RX_RECORD_TOO_LONG` を出す。
2. 録画中(予約か WebUI からの即時録画)に `time docker compose stop edcb` を実行し、所要時間と、録画ファイルが最後まで再生できるかを確かめる。`docker compose logs edcb` の末尾に `entrypoint: stopped` があり、終了コードが 0 であること。

## 実施記録

2026-10-05 実施。作業ブランチ `v2-phase-2-provision`(`v2` から作成)。

### 先に確認したこと(`facts.md` に反映)

- U3: `HttpPublic` 配下に実行時の書き込みが**ある**(EMWUI のサムネイル `video/thumbs/`、`XCODE_LOG` 有効時の `log/`)。6 章の判断基準により、`HttpPublic` はボリュームに残し、ハッシュで同期する方式にした。`HttpPublicFolder` は書かない。
- U4: F13。HTTP は IPv4 / IPv6 / IPv4 射影アドレスを混ぜて書ける。**TCP は混ぜるとすべて拒否される**ので、TCP の既定値は IPv4 だけにした。
- U5: F12。セクション名・キー名とも大文字小文字を区別しない。EDCB は BOM を読み飛ばさない。
- U6: F14。SIGTERM で正常に終了する。EpgTimerSrv はチューナーのプロセスを最大 30 秒待つので、`stop_grace_period` を 2 分にした。
- U7: `/var/local/edcb/ssl_cert.pem`。
- そのほか: Lua の `GetPrivateProfile` のパスの基準(F12)、`[SET_TCP] IP0=1` は SrvPipe(F15)、EMWUI の `Setting/HttpPublic.ini` は CP932(F12)。

### 行ったこと

**プロビジョニング(`edcb/rootfs/usr/local/lib/edcb-provision/edcb_provision/`、Python 標準ライブラリのみ)**

| モジュール | 役割 |
|---|---|
| `ini.py` | 行を保ったまま指定のキーだけを書き換える編集処理。EDCB と同じ規則で読む(F12)。BOM と改行コードを維持し、UTF-8 として読めないバイトもそのまま書き戻す。重複したキーは最初のものを書き換えて警告 |
| `config.py` | 設定の収集。環境変数(3.1 の表すべて)と上書き用 ini から、強制するキーと「無いときだけ」書く既定値の一覧を作る。優先順は環境変数 > 上書き用 ini > 既定値。不正な値は無視して警告。知らない `EDCB_*` 変数も警告(`EDCB_BACKEND_*` は除く) |
| `apply.py` | 一覧と現在の ini を比べて変更を計算する。既定値の「無いとき」は、変更前のファイルで判断する(`[SET_TCP]` の 3 キーを `Count` の有無でまとめて扱うため) |
| `fsutil.py` | 一時ファイル + rename での書き込み(既存ファイルは所有者とモードを維持、新しいファイルは `PUID:PGID`)、退避(`.provision/backup/<日時>/`、直近 5 世代) |
| `state.py` | 状態ファイル(`.provision/state.json`)。生成物とハッシュの記録。内容が同じなら書き直さない |
| `initfiles.py` | `make setup_ini` 相当の初期ファイルと、EMWUI の `Setting/` の初期ファイル(無いときだけ) |
| `httppublic.py` | `HttpPublic` の同期(`design.md` の 6 章) |
| `legacy.py` | Legacy WebUI の設定変更の許可(`.provision/webui.ini [LEGACY] ALLOW_SETTING`) |
| `provision.py` | 全体の流れと表示。変更が無ければ `provision: no changes` |
| `cli.py` | `edcbctl provision [--diff]`、`edcbctl allow-setting on\|off\|status` |
| `healthcheck.py` | HEALTHCHECK。EpgTimerSrv のプロセスと、HTTP が有効なら最初の `HttpPort` への接続 |
| `logtail.py` | デバッグログ(`EpgTimerSrvDebugLog.txt`、`EpgDataCap_Bon_DebugLog-*.txt`)を `[EpgTimerSrv] …` の形で標準出力へ |

**entrypoint(`edcb/rootfs/entrypoint.sh`、`edcb/entrypoint.sh` から移動して作り直し)**

- root でなければ、`PUID` / `PGID` への移行方法を出して終了する。
- `setpriv` で `PUID:PGID` に落とす。補助グループは、コンテナに渡されたグループ(`group_add`)から 0 を除いたものと、`/dev/dri/renderD*` の所有グループ。
- BonDriver の ini は従来どおり `MIRAKC_ADDRESS` を名前解決して書く。未指定なら `mirakc:40772`。**名前解決に失敗しても終了せず**、警告を出して続ける。
- `Setting/` が無いか空のとき(初回)だけ、`/var/local/edcb` の所有者を `PUID:PGID` にする。それ以外は書き込めるかを調べて警告するだけ。
- 終了時の動作(プロセスグループへの SIGTERM、`pidwait`)は v1 のまま。EpgTimerSrv が予期せず終了したときも子プロセスを止めてから終わる。

**Dockerfile**

- `python3`、`procps`、`tzdata` を追加。`ENV TZ=Asia/Tokyo`。
- ビルド時に `HttpPublic` 一式を `/usr/local/share/edcb/` に組み立て、`edcb/build/patch-legacy-util.sh` で `legacy/util.lua` の `ALLOW_SETTING=false` の行を置き換える(1 行でなければビルド失敗)。
- `chmod 777` / `chmod 666` を削除。`COPY rootfs/ /`。`HEALTHCHECK`(間隔 1 分、開始猶予 2 分)。`EXPOSE` に 5511、5520、5521 を追加。

**compose ほか**

- `compose.yml`: `env_file`(`./edcb.env`、`required: false`)、`./edcb/overrides` の読み取り専用マウント、ポート 4510 / 5510(ホスト側は `EDCB_HOST_TCP_PORT` / `EDCB_HOST_HTTP_PORT`。HTTPS と SSE 専用ポートは既定で公開しない。下の「レビューでの修正」)、`stop_grace_period: 2m`。`environment`(`TZ`、`MIRAKC_*`)は削除した(compose の `environment` は `env_file` より優先され、利用者が `edcb.env` で変えられなくなるため。既定値はイメージと entrypoint が持つ)。
- `compose.override-sample.yml`: `user:` の例を消し、`PUID` / `PGID` の案内に替えた。HTTPS と SSE 専用ポートを公開する例を足した。
- `edcb.env-sample` を作った。`edcb/overrides/.gitkeep` を足した(`.gitignore` も更新)。
- `chlegacyset.sh` を削除。Setup.md の該当箇所を `edcbctl allow-setting` に直し、ACL、`PUID` / `PGID`、初回に自動で入る設定の説明を最小限直した。
- `build.yml` に `test` ジョブ(`pipx run pytest -v edcb/tests`)を足した。
- `edcb/tests/`: pytest 55 件。

### 検証結果

- pytest: Python 3.12(`uv run --python 3.12 --with pytest`)で 55 件すべて成功。
- shellcheck 0.11(`entrypoint.sh`、`patch-legacy-util.sh` ほか)、actionlint 1.7.12: エラー 0。
- `docker compose config`: 一時ディレクトリの `compose.yml` 単体、sample を重ねたもの、`EDCB_HOST_HTTP_PORT=15510` で成功。
- 実データの ini のコピー(スクラッチ内)で、Docker を使わずにプロビジョニングを実行し、既存のキーが変わらないことと、2 回目が `no changes` になることを確認した。初期ファイル(`Bitrate.ini`、`BonCtrl.ini`)が `make setup_ini` の変換結果とバイト単位で一致することも確認した。

Docker が要る確認は、ユーザに sudo でスクリプトを 2 回実行してもらい、ログを読んで判断した(Docker 29.8.1)。コンテナは `edcbtest-*`、イメージは `edcb:v2test`、ポートは `127.0.0.1` の 15510〜15512、データは `/tmp/edcbtest.*`。1 回目は T1 だけ失敗した(起動直後のデバッグログが標準出力に出ない。下の「途中で直した点」)。以下は修正後の 2 回目の結果で、すべて成功した。

| # | 確認 | 結果 |
|---|---|---|
| T0 | `docker build edcb/` | 成功。ビルドログに `Patched …/legacy/util.lua` と置き換え後の行 |
| T0b | 上流の `util.lua` の `ALLOW_SETTING=false` を変えるパッチを足してビルド | 失敗する(`expected exactly one … found 0`) |
| T1 | 空のディレクトリで起動(mirakc は名前解決できない) | 3.1 の既定値がすべて書かれ、`HttpPort` は書かれない。EpgTimerSrv は uid 1000 で動き、`/legacy/` と `/E3/` が 200(ホストからの接続。既定の ACL で許可される)、TCP 4510 が接続を受ける。`docker logs` にデバッグログが出る。`Setting/HttpPublic.ini` は UTF-8。名前解決の失敗は警告だけ。healthy |
| T2 | 同じ構成で再起動 | `provision: no changes`。ini のハッシュが変わらない |
| T5 | `edcbctl allow-setting on/off`(再起動なし) | off の POST は `変更は許可されていません`、on の直後の POST は `変更しました`(`RecFileName` が書かれた)、off の直後は再び拒否。EpgTimerSrv の PID は変わらない |
| T12 | 許可したまま再起動 | `ALLOW_SETTING: "1" -> "0" (start-up state)`。POST は拒否される |
| T10 | `docker stop` | 約 3.2 秒、終了コード 0。デバッグログに `Received signal 15` → `Server finalized` → `LOG STOP`、entrypoint の `stopped` |
| T3 | `edcb/ini/*.ini` のコピーで起動 | 先に `edcbctl provision --diff` を実行し、何も書き換わらないことを確認。起動後の差分は追加だけ(`EpgTimerSrv.ini` に `HttpNumThreads`、`EnableTCPSrv`、`TCPAccessControlList`、`CompatFlags`、`EpgDataCap_Bon.ini` に `[SET_TCP]` の 3 キー)。既存の行の変更は 0 |
| T4 | WebUI 相当の変更をして再起動 | `SaveDebugLog=0`、`EnableTCPSrv=0`、`SaveLogo=0`、`[SET_TCP] Count=0`、追記した `StartMargin=10` はそのまま。環境変数で指定した `HttpNumThreads`(5 → 30)と `RecFolderPath0` は戻る。上書き用 ini の `BonCtrl.ini [EPGCAP] EpgCapTimeOut=20` は、その行だけが変わる(コメントと並びは同じ)。`readme.txt` は無視して警告。退避が作られる |
| T6 | `--group-add 1500 --group-add video --device /dev/dri` | EpgTimerSrv の補助グループが `44`(video)、`renderD128` の所有グループ、`1500` の 3 つ。0 は含まれない |
| T7 | `PUID=1234 PGID=1234 UMASK=002` | EpgTimerSrv の Uid / Gid が 1234。ボリューム内のファイルはすべて `1234:1234`(EDCB が後から作ったデバッグログも) |
| T8 | `--user 1000:1000` | 移行方法のメッセージを出して終了コード 1 |
| T9 | 名前解決できるが届かない接続先(`192.0.2.1`) | EpgTimerSrv が起動する |
| T11 | 上書き用 ini で `EnableHttpSrv=0` | healthy(`HTTP is off`)。EpgTimerSrv が動いていないと失敗する(rc=1)ことも確認 |
| T15 | 初回に `ssl_cert.pem` を置いて起動 | `HttpPort=5510,5520,5511s,5521s` が書かれ、`https://…:5511/E3/` が 200(COEP / COOP ヘッダあり)、HTTP の `/legacy/` も 200、healthy |

検証では、ヘルスチェックの待ち時間を短くするため `--health-interval=5s --health-start-period=60s` を付けた。

### 受け入れ条件の補足

- 「`docker stop` で EpgTimerSrv と子プロセスが残らずに終了する」: Docker の検証ではチューナーが無く、子プロセス(EpgDataCap_Bon)は動いていなかった。子プロセスを含む確認は実機で行い、録画中の EpgDataCap_Bon も正常に終了して、録画ファイルが閉じられることを確かめた(「実機確認の結果」)。
- 「接続先に届かない状態でも起動する」: 名前解決できない場合(T1)と、届かないアドレスの場合(T9)の両方で確認した。

### 途中で直した点

- 1 回目の検証の T1: ログ転送の Python が起動しきる前に EpgTimerSrv が書き始め、その行を「起動前からある行」として飛ばしていた。ログ転送が既存のログの大きさを測り終えてから EpgTimerSrv を起動するようにした。
- EMWUI の `Setting/HttpPublic.ini` が CP932 だったので、初回のコピー時に UTF-8 へ変換するようにした。v1 の利用者のボリュームにある既存のファイルには触らない。

### 設計から変えた点・実装時に決めた点

- `HttpPublic` はボリュームに残した(U3)。`HttpPublicFolder` は書かない。
- `EDCB_TCP_ACL` の既定値は IPv4 のプライベート帯だけ(設計では HTTP と同じ)。TCP の ACL は IPv4 と IPv6 を混ぜられないため(F13)。
- ホスト側のポートの変数名を `EDCB_HOST_TCP_PORT` / `EDCB_HOST_HTTP_PORT` にした。コンテナに渡す `EDCB_HTTP_PORT`(`HttpPort` の値)と名前が衝突するため。
- `make setup_ini` は呼ばず、同じ変換を Python で行う。`make setup_ini` は `HttpPublic/legacy/` を(置き換え前の `util.lua` で)コピーし、`EpgTimerSrv.ini` に `EnableHttpSrv=2` と localhost だけの ACL を書くので、同期と既定値が食い違うため。
- 5 章の手順 4(所有者)を手順 2 の前に行う。初回かどうかを、ファイルを作る前に判断するため。
- 許可の状態は `.provision/webui.ini [LEGACY] ALLOW_SETTING`。`--boot`(entrypoint が付ける。ヘルプには出さない)のときだけ起動時の状態に戻す。手動の `edcbctl provision` は戻さない。
- `edcbctl allow-setting` は、ボリューム内の `legacy/util.lua` が置き換え後のものでなければ警告して終了コード 1 にする。
- `compose.yml` から `environment`(`TZ`、`MIRAKC_*`)を消した。`TZ` の既定はイメージ、`MIRAKC_*` の既定は entrypoint が持つ。
- `EDCB_CHSCAN` は値の検査だけ行う(スキャンはフェーズ 4)。
- ヘルスチェックの HTTP は、接続できれば成功とする(ACL で 127.0.0.1 を外した利用者でも unhealthy にしないため)。
- ini に新しいキーを足す位置は、そのセクションの最後のキーの直後(キーが無ければ見出しの直後)。次のセクションの説明コメントの前に入る。
- `[SET_TCP]` の既定値は 3 キーをまとめて扱い、`Count` が無いときだけ書く。

### レビューでの修正

- **HTTPS と SSE 専用ポートを既定では公開しない**(ユーザと合意)。当初は `compose.yml` で 5511 / 5520 / 5521 も同じ番号で公開していた。2 台目の構成でホストの 5511 を HTTP(コンテナの 5510)に割り当てていると、HTTPS のつもりで開いたポートが HTTP につながり、ブラウザが `SSL_ERROR_RX_RECORD_TOO_LONG` を出す(実機で発生)。HTTPS を使う利用者が `compose.override.yml` で番号を選んで足す形にした。コンテナ内の番号は EMWUI の推奨(`5510,5520,5511s,5521s`)のまま。`EDCB_HOST_HTTPS_PORT`、`EDCB_HOST_SSE_PORT`、`EDCB_HOST_SSE_HTTPS_PORT` は廃止した。
- 修正後の `docker compose config`(`compose.yml` 単体、sample を重ねたもの)は成功し、公開されるのは 4510 と 5510 だけになった。イメージは変えていないので、Docker での検証(上の表)はやり直していない。

### 実機確認で見つかった不具合(mirakc イメージ)

- HTTPS で `/E3/` は開けたが、リモート視聴が読み込み中のまま進まなかった。トランスコードのログ(`Setting/HttpPublic.ini [XCODE] LOG=1`)では、ffmpeg への入力が空だった。
- 切り分けの結果、edcb 側ではなく mirakc 側の復号が原因だった。`decode=0` のストリームは流れるが、`decode=1` は 404 になり、`arib-b25-stream-test` が `B_CAS_CARD::init() : code=-3` で失敗していた。Debian の pcscd が polkit 有効でビルドされているため(`facts.md` の U14)。
- `mirakc/Dockerfile` の起動コマンドを `pcscd --disable-polkit` に直した(フェーズ 1 から引き継いだ不具合の修正。別のコミット)。動いているコンテナの中で pcscd を `--disable-polkit` 付きで起動し直したところ、復号できるようになった。修正したイメージで mirakc を作り直したあとも、TS-Live! で再生できることをユーザが確認した。
- フェーズ 5 で mirakc の entrypoint をスクリプトにするときも、このオプションを引き継ぐこと。
- 気づいた点: 視聴や録画の最中、EpgDataCap_Bon が状態の行(`Sig:27.26 D:0 S:0 sp:0 ch:7 Rec`)を改行なしで標準出力に書くので、`docker compose logs` でほかの行とつながって見える。動作には影響しない。EpgDataCap_Bon の標準出力を捨てるかどうかは、あとのフェーズで判断する。

### 実機確認の結果

| 確認 | 結果 |
|---|---|
| HTTPS で `/E3/` を開く(自己署名の証明書、コンテナの 5511 をホストの別の番号に割り当て) | 開けた(ブラウザは証明書の警告を出す) |
| HTTPS で TS-Live! のライブ視聴 | **再生できた**。Firefox と Chrome、地上波と BS で確認。mirakc の pcscd は、最初はコンテナの中で `--disable-polkit` 付きで起動し直した状態で、その後、修正したイメージでも確認 |
| HTTPS で HLS(`432p/h264/ffmpeg`)のライブ視聴 | **再生できない**(未解決。下記) |
| 録画中の `docker compose stop edcb` | **2.2 秒で停止**。EpgTimerSrv と EpgDataCap_Bon がそれぞれ `Received signal 15` を出して正常に終了し、entrypoint の `stopped` が出た。録画ファイル(約 36 MB、約 19 秒分)は大きさが 188 バイトの整数倍で、同期バイトの欠けとスクランブルのままのパケットは 0。ffmpeg で最後までデコードできた(先頭のエラーが数件だけ) |

HLS(`432p/h264/ffmpeg`)の症状:

- ブラウザは読み込み中のまま。`/api/mp4init` と `/api/segment` が 404 を返す(Firefox、Chrome とも)。
- トランスコードのログでは、ffmpeg は約 17 秒分を変換したあと、出力先が閉じて終了した(`Broken pipe`)。入力に AAC と MPEG-2 のデコードエラーがあり、出力の音声は約 8 kB しか無かった。tsmemseg(`-4`、fMP4)が初期化データを作れず、ブラウザがあきらめた、と見ている。
- v1 での利用者の視聴は、HTTP と例外の設定を使った TS-Live! だった。HLS 方式が v1 で動いていたかは確かめていない。v2 で壊れたのか、もともと動かないのかは未確認。フェーズ 5 の作業 3 に移した(フェーズ 5 の `ffmpeg-qsv` の実機確認も HLS 方式で行うため)。

### 次のフェーズへの申し送り

- **v1 からの移行(フェーズ 6)**: `user:` は使えなくなる(`PUID` / `PGID` へ)。`chlegacyset.sh` は無くなり、v1 で `ALLOW_SETTING=true` にしていた利用者も、初回の起動で禁止に戻る(`util.lua` が置き換わるため。常に許可するなら `EDCB_LEGACY_ALLOW_SETTING=true`)。初回の起動で `HttpPublic` の内容が違うファイルは退避して置き換わる(`.provision/backup/`)。旧 `HttpPublic/EMWUI/` は残る。TCP サーバが既定で有効になる(`EnableTCPSrv` が無かった利用者)。`compose.yml` の `environment` に書いていた `MIRAKC_*` は `edcb.env` か override へ。
- **フェーズ 3**: 接続先の処理は entrypoint のシェルに残している(`MIRAKC_ADDRESS` の名前解決)。プロビジョニングへ移すときは `config.py` の `_IGNORED_ENV_PREFIXES` から `EDCB_BACKEND_` を外す。BonDriver の ini は今も 3 つのシンボリックリンクで 1 ファイルを共有している。`/usr/local/lib/edcb` への書き込みは root のプロビジョニングで行える。生成物の管理には `state.py` の `record` / `is_ours` を使う。
- **フェーズ 4**: 状態ファイルには `httppublic` のセクションがある。`edcbctl` のサブコマンドは `cli.py` に足す。ChSet を書き換えたあとの再読み込み(U11)は未調査。
- **ini の文字コード**: プロビジョニングは UTF-8 として読み、読めないバイトはそのまま書き戻す。EDCB は BOM を読み飛ばさないので、BOM 付きの ini は先頭のセクションが EDCB から見えない(プロビジョニングは見える)。
