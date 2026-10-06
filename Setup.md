# セットアップ

v1 から更新する場合は、先に [v1 から v2 への移行手順](docs/migration-v1-to-v2.md) を読んでください。

コマンドは、このリポジトリを置いたフォルダで実行します。Docker の操作に root が必要な環境では、`sudo` を付けてください。

## 最短の手順

同梱の mirakc を使い、チューナーとカードリーダーがホストにつながっている場合です。

```sh
git clone https://github.com/yuta2k/docker-mirakc-edcb.git
cd docker-mirakc-edcb
git checkout v2.0.0                            # 使うリリースのタグ
cp mirakc/config-sample.yml mirakc/config.yml  # 編集する(「mirakc の設定」)
cp compose.override-sample.yml compose.override.yml  # 編集する(「compose.override.yml」)
docker compose up -d
docker compose logs -f edcb                    # 初回はチャンネルスキャンが終わるまで数分かかる
```

起動したら、ブラウザで `http://<ホストのアドレス>:5510/E3/` を開きます。

以下、各手順の説明です。

## 事前準備

* Docker Engine と Docker Compose 2.24.4 以降を入れる
* カードリーダーを、コンテナ内の pcscd で使うか、ホストの pcscd で使うかを決める([pcscd](#pcscd))  
  コンテナ内の pcscd を使う場合(既定)は、ホストの pcscd を止めます(`sudo systemctl disable --now pcscd.socket pcscd.service` など)
* 同じホストで、この構成をもう 1 つ動かしている場合は、先に [同じホストに構成を 2 つ置く場合](#同じホストに構成を-2-つ置く場合) を読む

## mirakc の設定

同梱の mirakc を使う場合は、`mirakc/config-sample.yml` をもとに `mirakc/config.yml` を作ります(git 管理外)。  
[ISDBScanner](https://github.com/tsukumijima/ISDBScanner) で生成することもできます。書き方は [mirakc のドキュメント](https://mirakc.github.io/dekiru-mirakc/stable/config/) を参照してください。

* **地上波専用・衛星専用のチューナーがある場合は、`tuners` で専用のチューナーを両対応のチューナーより先に書きます。** mirakc は空いているチューナーを書いた順に使うので、両対応のチューナーが地上波に使われて、衛星を受けられなくなるのを防ぎます。EDCB 側も、専用のチューナーを先に使うように設定します(初回の起動時に自動)
* mirakc の `channels` の並び順は、EDCB のチャンネル定義の番号になります。途中にチャンネルを足したり消したりしたら、EDCB でスキャンし直します([チャンネル定義](#チャンネル定義))

外部の mirakc / Mirakurun だけを使う場合は、`mirakc/config.yml` は要りません([接続先](#接続先))。

## compose.override.yml

`compose.yml` は全員共通の定義で、`git pull` で更新されます。**編集しないでください。** 環境ごとの設定は `compose.override.yml`(git 管理外)に書きます。`compose.override-sample.yml` をコピーして、必要な部分のコメントを外します。

* mirakc の `devices` に、チューナーのデバイスと、カードリーダーの USB(`/dev/bus/usb:/dev/bus/usb`)を書く
* edcb の `volumes` に、録画ファイルの保存先を書く(例: `/mnt/recorded:/recorded`)

重ね方の決まり:

* `devices`、`volumes` は `compose.yml` の定義に追加されます
* `environment` は、同じ変数名なら上書き、無ければ追加されます
* `ports` は追加されます。置き換えるときは `ports: !override` と書きます

書いた内容は `docker compose config` で確かめられます。

## edcb.env

EDCB の設定は、環境変数で指定できます。`edcb.env-sample` をコピーして `edcb.env`(git 管理外)を作り、必要な行だけを有効にします。**無くても起動します。**

```sh
cp edcb.env-sample edcb.env
```

変数の一覧は [環境変数](#環境変数) にあります。`compose.override.yml` の `environment` に書いても同じです。

## 実行ユーザ

EDCB は `PUID` / `PGID`(既定 `1000` / `1000`)のユーザで動きます。`compose.override.yml` の `user:` は使えません(指定すると、移行方法を表示して終了します)。

* `edcb/ini` は、初回の起動時(`edcb/ini/Setting/` が空のとき)に、このユーザの所有にします。2 回目以降は所有者を変えず、書き込めなければ警告します
* 録画ファイルの保存先は、このユーザが書き込めるようにしておきます
* 録画先を共有するグループがあれば、`compose.override.yml` の `group_add` で渡します
* 作るファイルの権限は `UMASK`(例: `002`)で変えられます

## ポートの公開

既定で公開するのは、TCP の 4510(EpgTimerNW など)と HTTP の 5510(WebUI)です。HTTPS などは [HTTPS](#https) で足します。

**Docker が公開したポートは、ホストのファイアウォール(ufw、firewalld など)の設定を通りません。** インターネットに直接つながるホストでは、公開するアドレスを LAN 側に限定してください。`.env`(このフォルダに作る。git 管理外)に、アドレス付きで書けます。

```sh
# .env
EDCB_HOST_TCP_PORT=192.168.0.10:4510
EDCB_HOST_HTTP_PORT=192.168.0.10:5510
```

ホスト側の番号だけを変える場合は `EDCB_HOST_HTTP_PORT=15510` のように書きます。`compose.override.yml` で足すポートも、`- 192.168.0.10:5511:5511` のようにアドレスを付けられます。

EDCB 自身も、接続元のアドレスで制限しています([アクセス制御](#アクセス制御))。

## 起動

```sh
docker compose up -d
```

初回はイメージのビルドに数分かかります。起動の様子は `docker compose logs -f edcb` で見られます。

初回の起動では、次のことを自動で行います。

1. EDCB の設定ファイルを作り、既定の設定を書く([初回に書かれる設定](#初回に書かれる設定))
2. 接続先(既定では同梱の mirakc)のチューナーを数え、BonDriver とチューナー数を設定する
3. チャンネルをスキャンし、チャンネル定義を作る。**終わるまで EDCB は起動しません**(49 チャンネルで約 6 分半)
4. EDCB を起動し、すぐに EPG を取得する

ログに `WARNING` が出ていたら、内容を確かめてください。設定の状態は次のコマンドで確かめられます。

```sh
docker compose exec edcb edcbctl backends
```

```
DEFAULT: http://mirakc:40772 (reachable)
  kind  BonDriver                   tuners  Count  ChSet4  view
  M     BonDriver_LinuxMirakc.so    4       4      yes     yes
  T     BonDriver_LinuxMirakc_T.so  0       -      no      no
  S     BonDriver_LinuxMirakc_S.so  0       -      no      no
  channels: 49 (GR 11, BS 26, CS 12)
  channel scan: 2026-10-06T12:00:00+0900; the channels are unchanged
```

`ChSet4` が `no` の BonDriver は、EDCB から使われません(チューナーが 0 本の種類は、わざとそうしています)。

## 初回に書かれる設定

`edcb/ini`(コンテナ内 `/var/local/edcb`)の ini に、**キーが無いときだけ**次の値を書きます。既にあるキーは変えないので、WebUI で変えた設定は残ります。

| ファイル | キー | 値 |
|---|---|---|
| `EpgTimerSrv.ini [SET]` | `HttpAccessControlList` | localhost とプライベートアドレス帯 |
| | `EnableTCPSrv`、`TCPAccessControlList` | `1`、localhost とプライベートアドレス帯(IPv4) |
| | `HttpNumThreads` | `50`(EMWUI の推奨) |
| | `HttpPort` | `ssl_cert.pem` があるときだけ `5510,5520,5511s,5521s` |
| | `EnableHttpSrv`、`SaveDebugLog` | `1`、`1` |
| | `CompatFlags` | `4095`(tkntrec 版の EpgTimerNW との互換) |
| `EpgTimerSrv.ini [BonDriver_*.so]` | `Count`、`Priority` など | 接続先のチューナー数([チューナー数](#チューナー数)) |
| `EpgTimerSrv.ini [TVTEST]` | 視聴に使う BonDriver | チューナーのある BonDriver すべて |
| `EpgDataCap_Bon.ini` | `SaveLogo`、`[SET_TCP]` | ロゴの保存、リモート視聴用の送信先(SrvPipe、`0.0.0.1:0`) |
| `Setting/HttpPublic.ini`、`Setting/XCODE_OPTIONS.lua` | | EMWUI の設定ファイル(無いときだけコピー) |

* 何を変えたかは、起動時のログに `provision:` で始まる行で出ます。変える前のファイルは `edcb/ini/.provision/backup/` に退避します(直近 5 回分)
* WebUI のファイル(`edcb/ini/HttpPublic/`)は、イメージの更新に合わせて入れ替えます。内容が違うファイルは退避してから置き換えます
* 起動せずに、何が変わるかだけを見るには `docker compose exec edcb edcbctl provision --diff`

## 環境変数

`edcb.env` か `compose.override.yml` の `environment` で指定します。**指定した変数に対応するキーは、起動のたびにその値で上書きします。** 指定していない変数のキーは、キーが無いときだけ既定値を書きます。値を変えたら、コンテナを作り直して反映します(`docker compose up -d`)。

### 基本

| 変数 | 内容 | 既定 |
|---|---|---|
| `PUID` / `PGID` | EDCB を動かすユーザとグループ | `1000` / `1000` |
| `UMASK` | 作るファイルの umask | (変えない) |
| `TZ` | タイムゾーン | `Asia/Tokyo` |
| `EDCB_HTTP_ACL` | WebUI に接続できるアドレス(`EpgTimerSrv.ini [SET] HttpAccessControlList`) | localhost とプライベートアドレス帯 |
| `EDCB_HTTP_PORT` | `HttpPort` の値(そのまま書く。`s` を付けると HTTPS) | `ssl_cert.pem` があれば `5510,5520,5511s,5521s` |
| `EDCB_HTTP_NUM_THREADS` | `HttpNumThreads`(1〜50) | `50` |
| `EDCB_TCP_ENABLE` | TCP サーバ(EpgTimerNW など)を使うか(`true` / `false`) | `true` |
| `EDCB_TCP_ACL` | TCP に接続できるアドレス(`TCPAccessControlList`)。IPv4 と IPv6 の規則を混ぜると、EDCB はすべて拒否します | localhost とプライベートアドレス帯(IPv4) |
| `EDCB_COMPAT_FLAGS` | `CompatFlags` | `4095` |
| `EDCB_REC_FOLDERS` | 録画保存フォルダ(`Common.ini` の `RecFolderPath<N>`)。カンマ区切り | (書かない) |
| `EDCB_LEGACY_ALLOW_SETTING` | Legacy WebUI からの設定変更を許可するか(`true` / `false`)。起動のたびにこの値に戻ります | `false` |
| `EDCB_EMWUI_ALLOW_SETTING_LIST` | EMWUI の設定ページから変更できる接続元(`Setting/HttpPublic.ini [SET] ALLOW_SETTING_LIST`) | (書かない。EMWUI の既定は `127.0.0.1,::1`) |
| `EDCB_CHSCAN` | `first`: チャンネル定義(`Setting/ChSet5.txt`)が無いときだけ起動時にスキャンする。`never`: しない | `first` |
| `EDCB_LOG_STDOUT` | EDCB のデバッグログを `docker compose logs` にも出すか | `true` |

### 接続先

`<名前>` は、英大文字で始まる英大文字と数字(32 文字まで)。アンダースコアは使えず、`T` と `S` は予約されています。

| 変数 | 内容 | 既定 |
|---|---|---|
| `EDCB_BACKEND_<名前>_URL` | 接続先の URL(`http://ホスト:ポート`)。ポートを省くと `40772` | (必須) |
| `EDCB_BACKEND_<名前>_TUNERS` | チューナー数。`auto` か、`M:2,T:2,S:0` の形 | `auto` |
| `EDCB_BACKEND_<名前>_PRIORITY` | BonDriver が mirakc / Mirakurun に送る優先度 | `10` |
| `EDCB_BACKEND_<名前>_DECODE` | mirakc / Mirakurun 側でスクランブルを解除させるか(`1` / `0`) | `1` |

使い方は [接続先](#接続先) を参照してください。v1 の `MIRAKC_ADDRESS` / `MIRAKC_PORT` も、`DEFAULT` の接続先として引き続き読みます(`EDCB_BACKEND_DEFAULT_URL` があればそちらが優先)。

### Compose(`.env` に書く)

| 変数 | 内容 | 既定 |
|---|---|---|
| `COMPOSE_PROJECT_NAME` | プロジェクト名。コンテナ名とボリューム名がこれから決まる | フォルダの名前 |
| `EDCB_HOST_TCP_PORT` | コンテナの 4510 を公開するホスト側のポート(`アドレス:ポート` も可) | `4510` |
| `EDCB_HOST_HTTP_PORT` | コンテナの 5510 を公開するホスト側のポート(同上) | `5510` |

## 上書き用 ini

環境変数が無い設定を固定したいときは、`edcb/overrides/` に ini を置きます。`edcb/ini/` の同じ相対パスのファイルに、**書いたキーだけ**を起動のたびに上書きします。

```ini
; edcb/overrides/BonCtrl.ini
[EPGCAP]
EpgCapTimeOut=20
```

* 例: `edcb/overrides/EpgTimerSrv.ini`、`edcb/overrides/Setting/HttpPublic.ini`
* 書いていないキーとセクション、コメントには触りません。対象のファイルが無ければ作ります
* ini 以外のファイル(`.lua`、`.txt` など)は無視します(警告が出ます)
* 環境変数と同じキーを書いた場合は、環境変数が優先します(警告が出ます)

**WebUI での設定との関係**: 環境変数と上書き用 ini で指定したキーは、WebUI で変えても、次の起動で指定した値に戻ります。WebUI で変えたい設定は、ここに書かないでください。録画マージンやプリセットなどの日常の設定は、WebUI で行います。

## WebUI での設定

日常の設定は、ブラウザから Legacy WebUI(`http://<ホストのアドレス>:5510/legacy/`)か EMWUI で行います。ini を直接編集することもできます(反映には `docker compose restart edcb`)。

Legacy WebUI からの設定変更は、既定で禁止しています。次のコマンドで、再起動せずに許可・禁止を切り替えられます。

```sh
docker compose exec edcb edcbctl allow-setting on      # 許可
docker compose exec edcb edcbctl allow-setting off     # 禁止
docker compose exec edcb edcbctl allow-setting status  # 今の状態
```

許可した状態は、コンテナの次の起動で禁止に戻ります。常に許可する場合は `EDCB_LEGACY_ALLOW_SETTING=true` を指定します。設定を終えたら禁止に戻しておくと安心です。

最初に行うとよい設定:

* 「設定メニュー - 基本設定 - 録画保存フォルダ」: `compose.override.yml` の `volumes` で渡した場所(環境変数 `EDCB_REC_FOLDERS` でも指定できます)

チューナー数、視聴に使う BonDriver、ロゴの保存、リモート視聴用の送信先は、初回の起動時に設定されます。

EMWUI の設定ページは、別の仕組みで許可します(既定は localhost からだけ)。許可する接続元を `EDCB_EMWUI_ALLOW_SETTING_LIST` で指定します。

### アクセス制御

WebUI(HTTP)と TCP の接続元は、初回の起動時に「localhost とプライベートアドレス帯」に限定されます。変える場合は `EDCB_HTTP_ACL` / `EDCB_TCP_ACL` を指定するか、`EpgTimerSrv.ini` を編集します。書式は `+` / `-` とアドレス(`/` で長さ)をカンマで並べたもので、最後に一致した規則が効きます。

* HTTP では、IPv4 の接続元が IPv4 射影アドレスに見えることがあるので、`+::ffff:192.168.0.0/112` のような規則も書きます(既定値には入っています)
* TCP では、IPv4 と IPv6 の規則を混ぜると、すべての接続が拒否されます

## 接続先

### 同梱の mirakc だけを使う(既定)

何も指定しなければ、同梱の mirakc(`http://mirakc:40772`)につなぎます。BonDriver は次の 3 つです。

| BonDriver | 用途 |
|---|---|
| `BonDriver_LinuxMirakc.so` | 地上波・衛星の両対応のチューナー(M) |
| `BonDriver_LinuxMirakc_T.so` | 地上波専用のチューナー(T) |
| `BonDriver_LinuxMirakc_S.so` | 衛星専用のチューナー(S) |

チューナーが無い種類の BonDriver は、EDCB から見えないようにします。

### 外部の mirakc / Mirakurun を使う

同梱の mirakc を使わない場合は、`compose.override.yml` で無効にし、接続先を指定します。

```yaml
# compose.override.yml
services:
  mirakc:
    profiles: [disabled]
```

```sh
# edcb.env
EDCB_BACKEND_DEFAULT_URL=http://192.168.0.10:40772
```

接続先にはホスト名も使えます。接続のたびに名前を引くので、相手のコンテナを作り直して IP アドレスが変わってもつながります。IPv6 アドレスは使えません。

### 複数の接続先

接続先ごとに `EDCB_BACKEND_<名前>_URL` を書きます。名前 `DEFAULT` 以外の接続先の BonDriver は、`BonDriver_LinuxMirakc_<名前>[_T|_S].so` になります。**ほかの接続先を書くと、`DEFAULT` は自動では作られません。** 同梱の mirakc も使う場合は、`DEFAULT` も書きます。

```sh
# edcb.env
EDCB_BACKEND_DEFAULT_URL=http://mirakc:40772
EDCB_BACKEND_VM_URL=http://192.168.0.20:40772
EDCB_BACKEND_VM_TUNERS=M:0,T:1,S:1
```

接続先を足したら、コンテナを作り直し(`docker compose up -d`)、その接続先をスキャンします(`docker compose exec edcb edcbctl chscan VM`。[チャンネル定義](#チャンネル定義))。

接続先に届かなくても、EDCB は起動します。前回取得した情報で設定し、警告を出します。

### チューナー数

`TUNERS` が `auto`(既定)のときは、接続先の `/api/tuners` から種類ごとの本数を数え、`EpgTimerSrv.ini` に `[BonDriver_*.so]` のセクションが無いときだけ書きます。以降は WebUI での変更を優先し、本数が実際と違うときは警告だけ出します。

`M:2,T:2,S:0` のように指定すると、起動のたびにその本数で上書きします(M は両対応)。

* **ほかのソフトウェアと共有している mirakc / Mirakurun では、本数を実際より少なめに指定します。** EDCB は指定した本数まで同時に録画しようとするので、ほかのソフトウェアがチューナーを使っていると、録画に失敗します
* 新しく書くセクションの優先順位(`Priority`)は、地上波専用・衛星専用を先、両対応を後にします。両対応のチューナーを衛星の録画で埋めて、地上波を録画できなくなるのを防ぐためです
* EDCB と mirakc は別々にチューナーを割り当てるので、mirakc の `config.yml` でも専用のチューナーを先に書きます([mirakc の設定](#mirakc-の設定))

### 視聴に使う BonDriver

EMWUI での視聴には、「設定メニュー - その他 - 視聴に使用するBonDriver」の一覧にある BonDriver だけが使われます。一覧は、初回の起動時に、チューナーのある BonDriver をすべて書きます。後から足した接続先は一覧に入らないので、Legacy WebUI で足してください(`edcbctl backends` の `view` の列で確かめられます)。

### 接続先を外したとき

環境変数から接続先を外したり、ある種類のチューナーを 0 本にしたりしても、その BonDriver のチャンネル定義や `EpgTimerSrv.ini` のセクションは自動では消しません。起動時に警告が出るので、次のコマンドで片付けます。

```sh
docker compose exec edcb edcbctl prune --diff   # 片付ける内容を表示するだけ
docker compose exec edcb edcbctl prune          # 退避を取ってから片付ける
docker compose restart edcb                     # 録画中でないことを確かめてから
```

残しておくと、EDCB が無くなった BonDriver に予約を割り当て、録画に失敗するおそれがあります。

* 自分で置いた・編集したチャンネル定義は消しません(警告します)
* `ChSet5.txt` のサービスは、ほかの接続先と共有していることがあるので消しません。消したい場合は `edcbctl chscan --all --rebuild`
* 外す BonDriver を指定した予約は書き換えません。件数を表示するので、WebUI で直してください

## チャンネル定義

EDCB のチャンネル定義は、`edcb/ini/Setting/` の `ChSet5.txt`(全体)と、BonDriver ごとの `<BonDriver 名>(LinuxMirakc).ChSet4.txt` です。

### 初回の自動スキャン

`Setting/ChSet5.txt` が無い状態で起動すると、すべての接続先をスキャンし、チャンネル定義を作ります(`EDCB_CHSCAN=first`、既定)。スキャンの結果は、地上波専用(`_T`)と衛星専用(`_S`)の BonDriver 用に分けます。

* スキャンには 1 チャンネルあたり 8 秒ほどかかります。終わるまで EDCB は起動しません
* スキャンが終わると、すぐに EPG を取得します
* 録画などでチューナーが空いていなかったチャンネルは、取りこぼします。警告が出たら、チューナーが空いているときに `edcbctl chscan <名前>` でやり直してください
* 自動でスキャンするのは `ChSet5.txt` が無いときだけです

### スキャンし直す

接続先を足したとき、mirakc 側のチャンネルの構成を変えたときは、明示的にスキャンし直します。

```sh
docker compose exec edcb edcbctl chscan DEFAULT        # 接続先を指定
docker compose exec edcb edcbctl chscan --all          # すべての接続先
docker compose exec edcb edcbctl chscan --all --rebuild  # ChSet5.txt も作り直す
docker compose restart edcb                            # 反映には再起動が要る
```

* EPG 取得対象、検索対象など、`ChSet5.txt` で変えたサービスの設定は引き継ぎます
* スキャンに失敗したときは、元のチャンネル定義のまま変えません
* スキャンのあとに表示される `edcbctl status` の内容で、録画中でないことを確かめてから再起動します

### ずれの警告が出たとき

起動のたびに、接続先のチャンネルの構成がスキャンしたときと同じかを比べます。違うと次のような警告が出ます。

```
provision: WARNING: backend DEFAULT: the channel list of the backend changed since the scan on ... EDCB may tune to the wrong channels; scan again with: edcbctl chscan DEFAULT
```

チャンネル定義の番号は、mirakc / Mirakurun のチャンネルの並び順で決まります。**そのままでは別のチャンネルを選局するおそれがあります。** `edcbctl chscan <名前>` でスキャンし直してください。

### 自分で用意したチャンネル定義を使う

[ISDBScanner](https://github.com/tsukumijima/ISDBScanner) の EDCB-Wine 用の出力などを使う場合は、`edcb/ini/Setting/` に置きます。ファイル名は BonDriver の名前に合わせます。

* `BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt`
* `BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt`
* `BonDriver_LinuxMirakc_S(LinuxMirakc).ChSet4.txt`
* `ChSet5.txt`

自動のスキャンをさせない場合は、`EDCB_CHSCAN=never` を指定します。

自分で置いた ChSet4 は、上書きも削除もしません。その接続先は `edcbctl chscan` でもスキャンしません。自動で作ったものに切り替えたい場合は `--force` を付けます(置いていたファイルは `edcb/ini/.provision/backup/` に退避します)。

```sh
docker compose exec edcb edcbctl chscan DEFAULT --force
```

## HTTPS

EMWUI のライブ視聴(TS-Live!)や PWA は、ブラウザの制約で HTTPS でないと動きません(localhost を除く)。EDCB は、証明書を置くと HTTPS でも待ち受けます。

1. 証明書と秘密鍵を 1 つのファイルにまとめ、`edcb/ini/ssl_cert.pem` に置く(EDCB を動かすユーザが読めるように)

   ```sh
   # 自己署名の証明書の例(subjectAltName はブラウザで開くアドレスに合わせる)
   openssl req -new -newkey rsa:2048 -nodes -x509 -days 3650 -sha256 \
     -subj /CN=edcb -addext "subjectAltName = IP:192.168.0.10" \
     -keyout key.pem -out cert.pem
   cat cert.pem key.pem > edcb/ini/ssl_cert.pem && rm key.pem cert.pem
   ```

2. `compose.override.yml` で、HTTPS(コンテナ内 5511)と EMWUI の通知用のポート(5520、5521)を公開する

   ```yaml
   services:
     edcb:
       ports:
         - 5520:5520
         - 5511:5511
         - 5521:5521
   ```

   EMWUI は通知に「ブラウザで開いたポート + 10」を使うので、ホスト側の番号を変えるときも 10 違いにします(例: `15511:5511` と `15521:5521`)。

3. `docker compose up -d` で作り直す
4. `https://<ホストのアドレス>:5511/E3/` を開く

`EpgTimerSrv.ini` に `HttpPort` が無ければ、`ssl_cert.pem` があるときに `5510,5520,5511s,5521s` を書きます。既に `HttpPort` がある場合(v1 から移行した場合など)は、`EDCB_HTTP_PORT=5510,5520,5511s,5521s` を指定するか、`HttpPort` を編集してください。

**`HttpPort` に `s` の付いたポートがあるのに `ssl_cert.pem` が無いと、EDCB は HTTP のポートも開かず、WebUI に接続できなくなります。** 証明書を外すときは、`HttpPort` から `s` の付いたポートも消してください(ヘルスチェックは unhealthy になります)。

## pcscd

カードリーダー(B-CAS)は、mirakc コンテナの pcscd から使います。2 通りの構成があります。

| 構成 | 書き方 | 向いている場合 |
|---|---|---|
| コンテナ内の pcscd(既定) | mirakc の `devices` に `/dev/bus/usb:/dev/bus/usb`。ホストの pcscd は止める | ホストでほかにカードリーダーを使わない |
| ホストの pcscd | mirakc の `volumes` に `/run/pcscd/pcscd.comm` をマウント(`compose.override-sample.yml` 参照)。USB は渡さない | ホストのほかのソフトウェアとカードリーダーを共有する |

* ソケットがマウントされていると、コンテナ内の pcscd は起動しません。`DISABLE_PCSCD=1` でも止められます
* どちらを使っているかと、コンテナの pcsc-lite の版が、`docker compose logs mirakc` に出ます。コンテナ内の pcscd を使うのに USB が渡されていないと、警告が出ます
* ホストの pcscd を使う場合、ホストとコンテナの pcsc-lite の版が違うと通信できないことがあります。ホストの pcsc-lite が 2.4.1 以降なら、古い版のクライアントも受け付けます(ホストの 2.5.1 とコンテナの 2.3.3 で動作を確かめています)

## ハードウェアエンコード(Intel)

EMWUI の視聴でのトランスコードに Intel の GPU を使う場合は、拡張用の見本 `edcb/hwaccel/intel/Dockerfile` でイメージを作ります(amd64 のみ)。配布するイメージにはドライバを入れていないためです。

元にする EDCB のイメージを先にビルドし、見本の `BASE_IMAGE` に指定します。

```sh
docker build -t edcb-base:local edcb/
```

```yaml
# compose.override.yml
services:
  edcb:
    build:
      context: edcb/hwaccel/intel
      args:
        - BASE_IMAGE=edcb-base:local
        # QSVEncC も入れる場合は版を指定する(https://github.com/rigaya/QSVEnc/releases)
        # - QSVENCC_VERSION=8.32
    devices:
      - /dev/dri
```

```sh
docker compose build edcb
docker compose up -d
docker compose exec edcb vainfo   # ドライバが読み込まれ、Enc の項目が並べば使える
```

* EDCB を更新するときは、`edcb-base:local` を先にビルドし直してから `docker compose build edcb` を実行します
* `/dev/dri/renderD*` の所有グループは自動で引き継ぐので、`group_add` は要りません
* 使えるようになる EMWUI の視聴の設定(`Setting/XCODE_OPTIONS.lua` の項目):
  * `720p/h264/ffmpeg-qsv`(QSV。第 12 世代 Core 以降など、Tiger Lake 以降の GPU)
  * `QSVENCC_VERSION` を指定した場合は、`720p/h264/QSVEncC` と `720p/hevc/QSVEncC` も使えます(Gen11 以前の GPU では `--backend vaapi` を足す必要があります)
  * Gen11 以前の GPU では QSV が使えず、VA-API だけになります。ffmpeg の `h264_vaapi` を使う項目は既定に無いので、`Setting/XCODE_OPTIONS.lua` に足します

## 同じホストに構成を 2 つ置く場合

本番用と検証用など、この構成を同じホストで 2 つ動かす場合の注意です。

* **フォルダの名前が同じだと、Compose のプロジェクト名が同じになります。** 片方での `docker compose up` がもう片方のコンテナを作り直し、`docker compose down` が削除します。片方のフォルダの `.env` に `COMPOSE_PROJECT_NAME=<別の名前>` を書いてください
* ホスト側のポートが重ならないようにします(`.env` の `EDCB_HOST_TCP_PORT`、`EDCB_HOST_HTTP_PORT` と、`compose.override.yml` で足したポート)
* 同じチューナーとカードリーダーを 2 つの mirakc で使うことはできません。2 つ目は、1 つ目の mirakc に接続先としてつなぐのが簡単です(`EDCB_BACKEND_DEFAULT_URL` と、mirakc を無効にする設定)
* プロジェクト名は `docker compose config` の最初の行(`name:`)で確かめられます

## KonomiTV をつなぐ

[KonomiTV](https://github.com/tsukumijima/KonomiTV) は同梱しませんが、EDCB をバックエンドとして使えます。**動作は保証しません。**

* EDCB 側: TCP サーバ(4510)は既定で有効です。KonomiTV の接続元のアドレスが `TCPAccessControlList` で許可されているか確かめます(プライベートアドレス帯は既定で許可。同じホストの Docker のネットワークも含みます)
* KonomiTV 側: `config.yaml` で、バックエンドを EDCB にし、EDCB の TCP のアドレスを指定します

  ```yaml
  general:
    backend: EDCB
    edcb_url: tcp://192.168.0.10:4510/
  ```

* KonomiTV の視聴は、EDCB の「視聴に使用するBonDriver」の一覧にある BonDriver を使います([視聴に使う BonDriver](#視聴に使う-bondriver))。録画とチューナーを取り合うので、必要に応じてチューナー数を調整してください

詳しくは KonomiTV のドキュメントを参照してください。

## 録画保存先が btrfs の場合

このイメージの EDCB には `edcb/patches/edcb/` のパッチを当てており、btrfs に録画する場合の既定の動作を変えています。

### 録画開始時の容量確保

EDCB は録画開始時に、番組全体の予定サイズ分の領域をあらかじめ確保します(`EpgTimerSrv.ini` の `KeepDisk=1`、既定で有効)。  
btrfs では空き容量が少ないと、この確保が数十秒から数分止まることがあります。  
40 秒を超えると EpgTimerSrv が録画アプリ(EpgDataCap_Bon)を強制終了し、`録画開始処理に失敗しました` となります。  
このとき録画保存先にはサイズ 0 のファイルが残り、空きのある別の録画フォルダへの切り替えも行われません。

このイメージでは既定で、btrfs 上では容量の確保を行いません。  
`edcb/ini/Write_Default.so.ini` を作成すると変更できます(録画開始ごとに読み込まれるため、再起動は不要です)。

```ini
[SET]
Prealloc=2
```

| 値 | 動作 |
|---|---|
| `0` | 確保しない |
| `1` | 確保する(上流の EDCB と同じ動作) |
| `2` | btrfs 上では確保しない(このイメージの既定。`compose.override.yml` のビルド引数 `EDCB_PREALLOC_DEFAULT` で変更可) |

確保をしない場合も `KeepDisk=1` のままにしてください。  
録画開始時の保存先フォルダの選択には、引き続き番組全体の予定サイズが使われます。

### 別の録画フォルダへ切り替える基準

録画保存フォルダを複数登録している場合、EDCB は空き容量が「予定サイズ + 200MB」以下のフォルダを避けて録画を開始し、録画中に書き込みに失敗すると空きが 200MB を超えるフォルダに切り替えます。  
この 200MB は `edcb/ini/EpgDataCap_Bon.ini` で変更できます(MB 単位。録画アプリの次回起動時から反映されます)。

```ini
[SET]
FreeFolderMinMB=40960
```

数十 GB 程度にすると、同時に始まる複数の録画が同じフォルダの空きを取り合ったり、録画の途中でファイルが別フォルダに分かれたりすることを減らせます。

### btrfs の運用上の注意

* 空き容量は余裕を持たせてください。`btrfs filesystem usage` の `Device unallocated` が無くなると、metadata の領域を増やせなくなり、書き込みの遅延やファイル作成の失敗(ENOSPC)が起きやすくなります。`btrfs balance start -dusage=N` で使用率の低い領域をまとめると回復できます
* 録画保存先をスナップショットの対象にすると、録画ファイルを削除してもスナップショットが残っている間は容量が戻りません

## EPG 取得

初回のスキャンのあとは、自動で EPG を取得します。それ以降は、EDCB の設定(既定では毎日 23:00)で取得します。今すぐ取得するには、Legacy WebUI などの [EPG取得] ボタンを押します。

失敗する場合は、次のコマンドで実行してログを見られます(録画中でないときに)。

```sh
docker compose exec edcb EpgDataCap_Bon -d BonDriver_LinuxMirakc.so -epgcap
```

## 動作の確認

`EpgDataCap_Bon` はコマンドラインから起動できます。`-h` でヘルプが出ます。

```sh
docker compose exec edcb EpgDataCap_Bon -h
```

例えば次のコマンドで、Ctrl+C を押すまで BS11 の Signal・Drop・Scramble のカウントなどを表示できます。BonDriver_LinuxMirakc の mirakc への接続エラーも表示されます。

```sh
docker compose exec edcb EpgDataCap_Bon -d BonDriver_LinuxMirakc.so -nid 4 -tsid 16528 -sid 211
```

EDCB のデバッグログは `docker compose logs edcb` に出ます(`[EpgTimerSrv]` で始まる行)。ファイルは `edcb/ini/EpgTimerSrvDebugLog.txt` などです。
