# 目標仕様

v2 が完成したときの姿です。各フェーズはこの仕様の一部を実装します。
ここに書かれていない細部は、`decisions.md` の意図に沿って実装者が決めて構いません。決めた内容は、フェーズファイルの「実施記録」に書いてください。

## 1. リポジトリの構成

```
compose.yml                     git 管理。全員共通の定義
compose.override-sample.yml     利用者が compose.override.yml を作るための見本
edcb.env-sample                 利用者が edcb.env を作るための見本
edcb/
  Dockerfile                    ARG の既定値が上流バージョンの唯一の定義場所
  patches/edcb/*.patch          EDCB へのパッチ(現在の edcb/patches/*.patch を移動)
  patches/bondriver/*.patch     BonDriver へのパッチ(フォーク作成までの置き場所)
  rootfs/                       イメージにそのままコピーするファイル
    entrypoint.sh
    usr/local/bin/edcbctl
    usr/local/lib/edcb-provision/   プロビジョニングの Python コード
  hwaccel/intel/Dockerfile      Intel のハードウェアエンコードを足す拡張用の見本
  tests/                        pytest と、偽の Mirakurun API サーバ
  ini/                          利用者のデータ(git 管理外。/var/local/edcb にマウント)
  overrides/                    利用者の上書き用 ini(git 管理外。/etc/edcb/overrides にマウント)
mirakc/
  Dockerfile
  entrypoint.sh
  config-sample.yml
.github/workflows/
docs/
```

`.gitignore` に `compose.override.yml`、`edcb.env`、`.env`、`edcb/overrides/*` を追加し、`compose.yml` を外す。

## 2. compose.yml

- **共通側にホスト固有の値を書かない。** チューナーの `devices`、録画先の `volumes` は `compose.override.yml` に書く。
- **`container_name` を書かない。名前付きボリュームに `name:` を書かない**(`decisions.md` の D5)。mirakc の EPG キャッシュのボリュームは `mirakc-epg` というキーだけで定義し、実際の名前はプロジェクト名から決まるようにする。
- **プロジェクト名はフォルダ名から決まる。** 同じ名前のフォルダに clone した構成が同じホストに 2 つあると、Compose は両方を同じプロジェクトとして扱い、片方での `up` がもう片方のコンテナを作り直し、`down` が削除する。2 つ目の構成では `.env` に `COMPOSE_PROJECT_NAME=<別の名前>` を書く。これは `Setup.md` に注意として載せる。
- edcb サービス:
  - `image:` に GHCR のイメージ、`build:` にローカルビルドの両方を書く(pull できなければビルドできる)
  - `env_file` は `./edcb.env` を `required: false` で読む
  - `depends_on` は mirakc を `required: false` で指定する
  - ポートは `${EDCB_HOST_HTTP_PORT:-5510}:5510` のように変数にする。変数名は `EDCB_HOST_TCP_PORT`、`EDCB_HOST_HTTP_PORT`(`.env` に書く。コンテナに渡す `EDCB_HTTP_PORT` と混同しないよう `HOST` を入れた)
  - 既定で公開するのは 4510(TCP)と 5510(HTTP)だけ。HTTPS(コンテナ内 5511)と EMWUI の SSE 専用ポート(5520 / 5521)は、`compose.override-sample.yml` の例から利用者が足す(2026-10-05 にユーザと合意。2 台目の構成でホストの 5511 を HTTP に使っている場合などと衝突させないため)。EMWUI は SSE に「ブラウザで開いたポート + 10」を使うので、ホスト側も 10 違いにする
  - `stop_grace_period: 2m`(U6。EpgTimerSrv はチューナーのプロセスを最大 30 秒待つ。`facts.md` の F14)
  - ボリューム: `./edcb/ini:/var/local/edcb`、`./edcb/overrides:/etc/edcb/overrides:ro`
- 単一のファイルをマウントする箇所(`./mirakc/config.yml` など)は、長い書式で `bind: { create_host_path: false }` を指定する。短い書式だと、ファイルが無いときに Docker が同名のディレクトリを root 所有で作ってしまう。
- mirakc サービスは既定で有効。使わない利用者は `compose.override.yml` に次を書いて無効にする。

```yaml
services:
  mirakc:
    profiles: [disabled]
```

## 3. 環境変数

`edcb.env` または `compose.override.yml` の `environment` で指定する。**指定された変数に対応するキーは、毎起動で上書きされる。** 指定が無い変数は、キーが無いときだけ「既定値」を書く(「—」は何も書かない)。

### 3.1 基本

| 変数 | 書き込み先 | 既定値(キーが無いとき) |
|---|---|---|
| `PUID` / `PGID` | 実行ユーザ | `1000` / `1000` |
| `UMASK` | 実行時の umask | — |
| `TZ` | タイムゾーン | — |
| `EDCB_HTTP_ACL` | `EpgTimerSrv.ini [SET] HttpAccessControlList` | localhost + プライベート帯(IPv4、IPv4 射影アドレス、IPv6 の ULA / リンクローカル。`facts.md` の F13) |
| `EDCB_HTTP_PORT` | `EpgTimerSrv.ini [SET] HttpPort`(値をそのまま書く) | `ssl_cert.pem` があれば `5510,5520,5511s,5521s`、無ければ — |
| `EDCB_HTTP_NUM_THREADS` | `EpgTimerSrv.ini [SET] HttpNumThreads` | `50` |
| `EDCB_TCP_ENABLE` | `EpgTimerSrv.ini [SET] EnableTCPSrv`(`true` / `false`) | `true` |
| `EDCB_TCP_ACL` | `EpgTimerSrv.ini [SET] TCPAccessControlList` | localhost + プライベート帯(IPv4 のみ。TCP は IPv4 と IPv6 の規則を混ぜるとすべて拒否するため。F13) |
| `EDCB_COMPAT_FLAGS` | `EpgTimerSrv.ini [SET] CompatFlags` | `4095` |
| `EDCB_REC_FOLDERS` | `Common.ini [SET] RecFolderNum` と `RecFolderPath<N>`(カンマ区切り) | — |
| `EDCB_LEGACY_ALLOW_SETTING` | Legacy WebUI からの設定変更を許可するかの**起動時の状態**(`true` / `false`)。3.3 参照 | `false`(毎起動でこの値に戻す) |
| `EDCB_EMWUI_ALLOW_SETTING_LIST` | `Setting/HttpPublic.ini [SET] ALLOW_SETTING_LIST`(EMWUI で設定変更を許可する接続元) | — |
| `EDCB_CHSCAN` | スキャンの動作(`first` / `never`) | `first` |
| `EDCB_LOG_STDOUT` | デバッグログを標準出力にも流す(`true` / `false`) | `true` |

このほか、キーが無いときだけ次を書く(対応する環境変数は無い。変えたい利用者は上書き用 ini か WebUI を使う)。

- `EpgTimerSrv.ini [SET] EnableHttpSrv=1`(アクセスログを作らない設定。`make setup_ini` が `2` を書いた直後は `1` に直す)
- `EpgTimerSrv.ini [SET] SaveDebugLog=1`
- ~~`EpgTimerSrv.ini [SET] HttpPublicFolder=<イメージ内のパス>`~~(U3 の結果、`HttpPublic` はボリュームに残すので書かない。6 章)
- `EpgDataCap_Bon.ini [SET] SaveLogo=1`、`SaveLogoTypeFlags=32`
- `EpgDataCap_Bon.ini [SET_TCP] Count=1`、`IP0=1`、`Port0=0`(SrvPipe = `0.0.0.1:0`。EMWUI のリモート視聴用。3 つで 1 つのリストなので、`Count` が無いときだけ書く。`Count=0` は利用者が無効にした状態)
- `EnableHttpSrv=1` は、`make setup_ini` を使わずに初期ファイルを作る(5 章)ため、`2` が書かれることはない

### 3.2 接続先

`<名前>` は英大文字で始まる英大文字と数字の列。`T`、`S` は使えない。アンダースコアも使えない。

| 変数 | 意味 | 既定値 |
|---|---|---|
| `EDCB_BACKEND_<名前>_URL` | 接続先。`http://ホスト:ポート` | (必須) |
| `EDCB_BACKEND_<名前>_TUNERS` | チューナー数。`auto` または `M:2,T:2,S:0` の形(M は両対応) | `auto` |
| `EDCB_BACKEND_<名前>_PRIORITY` | BonDriver の `PRIORITY` | `10` |
| `EDCB_BACKEND_<名前>_DECODE` | BonDriver の `DECODE_B25`(`0` / `1`) | `1` |

- 名前 `DEFAULT` は特別で、BonDriver のファイル名に名前が付かない(`BonDriver_LinuxMirakc[_T|_S].so`)。
- **互換**: `MIRAKC_ADDRESS` と `MIRAKC_PORT` が指定されていて `EDCB_BACKEND_DEFAULT_URL` が無いとき、`http://$MIRAKC_ADDRESS:$MIRAKC_PORT` を `DEFAULT` として扱う。v1.0.4 以前の綴り違い(`MIRKAC_*`)も引き続き読む。
- 接続先が 1 つも指定されていないときは、`DEFAULT` を `http://mirakc:40772` として扱う(同梱の mirakc サービス)。
- 不正な名前や URL はエラーにせず、その接続先だけ無視して警告を出す(原則 E1)。

### 3.3 Legacy WebUI からの設定変更の許可(起動中に切り替えられること)

**コンテナを再起動せずに切り替えられる必要がある**(再起動は録画を中断するため)。環境変数は起動時の状態を決めるだけで、起動中の切り替えは `edcbctl allow-setting on|off` で行う。

- 許可の状態は、`/var/local/edcb/.provision/webui.ini` の `[LEGACY] ALLOW_SETTING`(`1` / `0`)に持つ。Lua からは `edcb.GetPrivateProfile(...,'.provision/webui.ini')` でリクエストのたびに読めるので、書き換えた直後から効く。ファイルが無い・読めないときは禁止。
- `legacy/util.lua` の `ALLOW_SETTING=true` / `false` の行を、上記のキーを読む式に**イメージのビルド時に**置き換える。置き換える行が見つからなければビルドを失敗させる(上流の変更に気づけるように)。起動のたびに `util.lua` を書き換える方式にはしない。
- 起動時は、`EDCB_LEGACY_ALLOW_SETTING` の値(未指定なら `false`)に必ず戻す。起動中に `edcbctl` で許可した状態は、次の起動までしか続かない。常に許可したい利用者は `EDCB_LEGACY_ALLOW_SETTING=true` を指定する。
- `edcbctl allow-setting status` で現在の状態を表示する。
- **EMWUI の設定ページは、この切り替えの対象外。** EMWUI は `Setting/HttpPublic.ini [SET]` の `ALLOW_SETTING` と `ALLOW_SETTING_LIST` をリクエストのたびに読む(`facts.md` の F6)。もともと起動中に変更でき、既存の利用者の設定を変えないため、プロビジョニングは `EDCB_EMWUI_ALLOW_SETTING_LIST` が指定されたときだけ `ALLOW_SETTING_LIST` を書く。

### 3.4 利用者が WebUI で設定した値の保持

プロビジョニングが値を上書きするのは、次の 2 つの場合だけ。それ以外のキーは、どのファイルのものでも触らない。

1. 環境変数、または上書き用 ini で**利用者が明示したキー**(毎起動で上書き。変更内容をログに出す)
2. キーが**存在しない**ときの既定値

Legacy WebUI は、オフにした項目を「キーの削除」ではなく `0` の書き込みで表す(`SaveLogo`、`SaveDebugLog`、`[SET_TCP] Count` などで確認済み)。そのため、利用者が WebUI でオフにした項目を既定値で戻してしまうことはない。**値が `0` や空文字のキーも「存在する」として扱うこと。**

## 4. 上書き用 ini

- `/etc/edcb/overrides/` に置いた ini を、`/var/local/edcb/` の同じ相対パスのファイルへ反映する。例: `overrides/EpgTimerSrv.ini`、`overrides/Setting/HttpPublic.ini`、`overrides/BonCtrl.ini`。
- 書かれているキーだけを上書きする。書かれていないキーとセクションには触らない。
- 対象のファイルが無ければ作る。
- 環境変数と同じキーが指定されていたら、環境変数を優先し、警告を出す。
- ini 以外のファイル(`.lua`、`.txt` など)は対象外。置かれていたら無視して警告する。

## 5. 起動時の処理(entrypoint)

root で開始し、次の順に行う(フェーズ 2 の実装では、4 の所有者の判断を 2 の前に行う。初回かどうかを、プロビジョニングがファイルを作る前に判断するため)。**どの段階で失敗しても、可能な限り EpgTimerSrv の起動まで進む。** 進めないのは、root で起動されていない場合だけ(エラーメッセージで `PUID` / `PGID` への移行を案内して終了する)。

1. SrvPipe の残骸(`/var/local/edcb/*.fifo`)を消す
2. `make setup_ini` 相当の初期ファイルを作る(無いものだけ)。`make setup_ini` は呼ばず、プロビジョニングが同じ変換(CP932 → UTF-8、CR の削除、`.dll` → `.so`)で `Bitrate.ini`、`BonCtrl.ini`、`ContentTypeText.txt` を作る。`HttpPublic` のコピーは 6 章の同期で行う
3. プロビジョニングを実行する(5.1)
4. `/var/local/edcb` の所有者を確認する。`PUID` / `PGID` で書き込めなければ警告を出す(`chown -R` を無断で行わない。初回で `Setting/` が空のときだけ所有者を設定する)
5. `EDCB_LOG_STDOUT` が有効なら、デバッグログを標準出力へ流す処理を起動する
6. `PUID` / `PGID` に権限を落として `EpgTimerSrv` を起動する(`setpriv` を使う)
   - 補助グループを落とさないこと。compose の `group_add` で渡されたグループを引き継ぐ
   - `/dev/dri/renderD*` が存在すれば、そのデバイスの所有グループも補助グループに加える(ハードウェアエンコード用。ホストごとに GID が違うため、利用者に指定させない)
7. 終了シグナルを受けたら、EpgTimerSrv と子プロセスすべてに SIGTERM を送り、終了を待つ(現在の `terminate_edcb` の動作を維持)

### 5.1 プロビジョニングの手順

1. 環境変数と上書き用 ini を読み、「書き込むキーの一覧」を作る
2. 接続先ごとに `/api/tuners` と `/api/channels` を取得する
   - タイムアウトは短くし、全体で待つ時間に上限を設ける(既定 30 秒程度)
   - 成功したら `/var/local/edcb/.provision/backend-<名前>.json` に保存する
   - 失敗したら保存済みの結果を使い、警告を出す。保存も無ければ、その接続先はチューナー 0 本として続ける
3. 接続先ごとに BonDriver を生成する(7 章)
4. チャンネル定義を処理する(8 章)
5. チューナー数を `EpgTimerSrv.ini` に書く(7.3)
6. 変更するファイルを `/var/local/edcb/.provision/backup/<日時>/` に退避する(直近 5 世代を残す)
7. ini を書き換える。書き換えは一時ファイルに書いてから rename する
8. 何を変えたかを標準出力に出す(ファイル、セクション、キー、変更前と変更後の値。ACL 以外に秘密情報は無いので値も出してよい)

`--diff` を付けて実行したときは、6 と 7 を行わず、8 の内容だけを表示する。

### 5.2 ini の読み書き

- **Python の `configparser` で書き戻さない。** コメント、キーの順序、大文字小文字、空行が失われる。行単位で読み、対象のキーの行だけを書き換える小さな編集処理を自前で持つ。
- 文字コードは UTF-8。BOM があれば維持する。改行コードは既存のファイルに合わせる(新規作成時は LF)。
- キー名の大文字小文字の扱いは、U5 の確認結果に合わせる。
- 同じセクション・キーが複数あるファイルに出会ったら、最初のものを書き換え、警告を出す。

### 5.3 状態ファイル

`/var/local/edcb/.provision/state.json` に、プロビジョニングが生成したファイルとそのハッシュを記録する。

- 生成物を上書き・削除してよいのは、記録があり、ハッシュが一致する(利用者が編集していない)ときだけ。
- 記録が無い、またはハッシュが違うファイルは「利用者のもの」として扱い、触らずに警告する。

## 6. HttpPublic の置き場所

- イメージ内(例 `/usr/local/share/edcb/HttpPublic`)に EDCB の `ini/HttpPublic` と EMWUI の `HttpPublic` を合わせて置き、`HttpPublicFolder` で参照させる。
- 設定変更の許可(3.3)のための `util.lua` の置き換えは、ビルド時に済ませる。起動時にイメージ内のファイルを書き換えない。
- EMWUI の `Setting/`(`HttpPublic.ini`、`XCODE_OPTIONS.lua`)は、従来どおり `/var/local/edcb/Setting/` に、無いときだけコピーする。
- **判断基準**: U3 の確認で、`HttpPublic` 配下に実行時に書き込む処理が 1 つでも見つかったら、イメージへの移動をやめる。その場合は現在の配置(ボリューム内)のままにし、「イメージ側のファイル一式のハッシュが前回と変わっていたら、ボリューム側を退避してから全体を入れ替える」方式にする。
- **U3 の結果(フェーズ 2)**: 書き込む処理があった(EMWUI のサムネイル、トランスコードのログ)。ボリューム内に置き、次のように同期する(`edcb_provision/httppublic.py`)。
  - イメージ内の一式は `/usr/local/share/edcb/HttpPublic`(EDCB の `index.html`、`favicon.ico`、`legacy/` と、EMWUI の `HttpPublic/`)。`util.lua` の置き換えはビルド時に済ませる。
  - 一式のハッシュが状態ファイルの記録と違うときだけ、ボリューム側で内容が違うファイルを退避して上書きし、無いファイルを足す。前回入れたが今回の一式に無いファイルは、変更されていなければ退避して消す。
  - それ以外のファイル(サムネイル、ログ、旧 `EMWUI/`)には触らない。ハッシュが同じときは、消えたファイルを戻すだけ。
- 既存の利用者のボリュームに残る `HttpPublic/` は消さない。README で「不要になった」と案内する。

## 7. BonDriver とチューナー

### 7.1 生成するファイル

接続先ごとに、`/usr/local/lib/edcb/` へ次の 3 組を起動時に作る。元の `.so` の**コピー**で作る(シンボリックリンクにしない)。

| 種別 | ファイル名(`DEFAULT`) | ファイル名(名前 `VM`) | 用途 |
|---|---|---|---|
| M | `BonDriver_LinuxMirakc.so` | `BonDriver_LinuxMirakc_VM.so` | 地上波・衛星の両対応チューナー |
| T | `BonDriver_LinuxMirakc_T.so` | `BonDriver_LinuxMirakc_VM_T.so` | 地上波専用チューナー |
| S | `BonDriver_LinuxMirakc_S.so` | `BonDriver_LinuxMirakc_VM_S.so` | 衛星専用チューナー |

それぞれに `<ファイル名>.ini` を作り、`SERVER_HOST`、`SERVER_PORT`、`SERVER_TYPE="http"`、`DECODE_B25`、`PRIORITY`、`SERVICE_SPLIT=0` を書く。`SERVER_HOST` にはホスト名をそのまま書く(BonDriver 側で名前解決する。フェーズ 3 のパッチ)。

### 7.2 チューナーの分類(`TUNERS=auto` のとき)

`/api/tuners` の各チューナーの `types` で分類し、本数を数える。

| `types` の内容 | 種別 |
|---|---|
| `GR` を含み、`BS` または `CS` も含む | M |
| `GR` を含み、`BS` も `CS` も含まない | T |
| `GR` を含まず、`BS` または `CS` を含む | S |
| それ以外(`SKY` のみなど) | 数えない(警告) |

### 7.3 EpgTimerSrv.ini への書き込み

- 種別ごとに、本数が 1 以上で、`[<BonDriver ファイル名>]` セクションが無ければ、`Count=<本数>`、`GetEpg=1`、`EPGCount=0`、`Priority=<連番>` を書く。
- セクションが既にあり、`TUNERS=auto` で `Count` が実際の本数と違うときは、警告だけ出す。
- `TUNERS` が明示されているときは、`Count` を毎起動で上書きする。
- `Priority` の連番は、既存のセクションの最大値の次から振る。

EDCB は ChSet4 がある BonDriver だけを認識する(`facts.md` の F3)ので、本数 0 の種別は ChSet4 を作らないことで無効にする(8.3)。

## 8. チャンネル定義

### 8.1 スキャン

- スキャンは接続先ごとに、**種別 M の BonDriver** で行う(本数が 0 でも、スキャン用には使える)。`EpgDataCap_Bon -d <M の BonDriver>.so -chscan`。
- スキャン結果の ChSet4 は、`/var/local/edcb/.provision/scan-<名前>.ChSet4.txt` に移して保存する(分割の元データ)。
- スキャン時の `/api/channels` の内容(`type` と `channel` の並び)のハッシュを、状態ファイルに記録する。

### 8.2 自動で実行する条件

- `EDCB_CHSCAN=first`(既定)で、`Setting/ChSet5.txt` が存在しないときだけ、起動時に全接続先をスキャンする。この間、EpgTimerSrv の起動は待たされる。
- `ChSet5.txt` が既にあるときは、スキャン結果が無い接続先があっても自動では実行しない。警告で `edcbctl chscan <名前>` を案内する。
- 利用者が置いた ChSet4(状態ファイルに記録が無いもの)がある接続先は、スキャンも分割も行わない。

### 8.3 分割

保存したスキャン結果から、種別ごとの ChSet4 を作る。

- space と種類の対応は、`/api/channels` を BonDriver と同じ規則(`facts.md` の F4。同じ `type` が連続する区間ごとに space を 1 つ)でたどって求める。
- M: 全行。T: `GR` の space の行だけ。S: `BS` と `CS` の space の行だけ。space と ch の値は変えない。
- 本数が 1 以上の種別だけ、`Setting/<BonDriver 名>(LinuxMirakc).ChSet4.txt` を作る。本数が 0 の種別のファイルは、自分が生成したものであれば削除する。
- 文字コードは UTF-8(BOM 付き)。改行コードはスキャン結果に合わせる。

### 8.4 ずれの検知

起動のたびに、`/api/channels` のハッシュをスキャン時のものと比べる。違っていたら、警告を出す(「mirakc 側のチャンネル構成が変わった。`edcbctl chscan <名前>` を実行すること。そのままだと別のチャンネルを選局するおそれがある」)。

## 9. edcbctl

コンテナ内で `docker compose exec edcb edcbctl <サブコマンド>` として使う。

| サブコマンド | 動作 |
|---|---|
| `provision [--diff]` | プロビジョニングを実行する。`--diff` は表示だけ |
| `allow-setting on\|off\|status` | Legacy WebUI からの設定変更の許可を、起動中に切り替える(3.3) |
| `backends` | 接続先ごとの到達可否、チューナー数(実際 / 設定)、チャンネル構成のずれの有無を表示する |
| `chscan [<名前> \| --all] [--rebuild]` | スキャンして分割まで行う。`--rebuild` は ChSet5 を作り直す(下記) |
| `status` | 録画中か、次の予約の開始時刻を表示する(U13 で手段が見つかった場合) |

- `chscan --rebuild` は、ChSet5 を退避してから削除し、全接続先をスキャンし直す。古い ChSet5 にあった利用者のフラグ(EPG 取得対象、検索対象)は、ONID / TSID / SID が一致するサービスに引き継ぐ。
- ChSet を変更したあとは、EpgTimerSrv に読み直させる必要がある。U11 で手段が見つかればそれを呼ぶ。見つからなければ「`docker compose restart edcb` を実行してください」と表示する。

## 10. ヘルスチェック

Dockerfile の `HEALTHCHECK` で、`EpgTimerSrv` のプロセスが生きていることを確認する。HTTP が有効なら `http://127.0.0.1:<ポート>/` への応答も確認する。HTTP を無効にしている利用者で失敗しないこと。

## 11. mirakc コンテナ

- entrypoint をスクリプトにする。`/run/pcscd/pcscd.comm` がソケットとして存在すれば、内蔵の pcscd を起動しない。無ければ従来どおり起動する。
- 環境変数 `DISABLE_PCSCD=1` でも内蔵の pcscd を止められるようにする(Mirakurun と同じ名前)。
