# docker-mirakc-edcb

Linux 版 EDCB(EpgTimerSrv / EpgDataCap_Bon)を、BonDriver_LinuxMirakc 経由で mirakc / Mirakurun につなぐ Docker Compose の構成です。

* [xtne6f 版 EDCB](https://github.com/xtne6f/EDCB)
* [EDCB_Material_WebUI](https://github.com/EMWUI/EDCB_Material_WebUI)(EMWUI)
* [BonDriver_LinuxMirakc](https://github.com/matching/BonDriver_LinuxMirakc)
* [mirakc](https://github.com/mirakc/mirakc)

> **v1(2025 年までの版)から更新する方へ**
> v2 では `compose.yml` をこのリポジトリで管理するようになりました。手元に自分で作った `compose.yml` があると、`git pull` が
> `untracked working tree files would be overwritten by merge: compose.yml` で止まります。
> **`git pull` の前に [v1 から v2 への移行手順](docs/migration-v1-to-v2.md) を読んでください。**

## 特徴

* EDCB の設定を起動時に自動で整えます。チューナー数、チャンネル定義(初回の自動スキャンと、地上波用 / 衛星用への分割)、WebUI のアクセス制御、EMWUI の視聴に要る設定などです。WebUI で変えた設定は、明示的に指定しない限り上書きしません
* 複数の mirakc / Mirakurun につなげます(コンテナ外のものを含む)
* EDCB などの上流のバージョンをコミットで固定し、パッチ込みのビルドを CI で確かめています
* 録画中の再起動や更新で録画を切らないための確認コマンド(`edcbctl status`)があります

## 構成

| | 内容 |
|---|---|
| `edcb` サービス | EDCB(EpgTimerSrv、EpgDataCap_Bon)、EMWUI と Legacy WebUI、BonDriver_LinuxMirakc、起動時の設定処理と `edcbctl` |
| `mirakc` サービス | mirakc と、スクランブル解除用の libaribb25 と pcscd。外部の mirakc / Mirakurun だけを使う場合は無効にできます |

同梱しないもの:

* リバースプロキシ。HTTPS は EDCB 自身の機能で、証明書を置くと有効になります
* KonomiTV などの視聴アプリ。接続例は [Setup.md](Setup.md#konomitv-をつなぐ) にあります(動作は保証しません)
* ハードウェアエンコードのドライバ。Intel 用の拡張の見本(`edcb/hwaccel/intel/`)があります

対応する接続先:

* mirakc: 対応(同梱のもの、外部のもの)
* Mirakurun: 対応。この構成が使う API(`/api/channels`、`/api/tuners`)の形が mirakc と同じことを、Mirakurun のソースで確かめています。Mirakurun の実機では確かめていません

## 必要なもの

* Docker Engine と Docker Compose **2.24.4 以降**(`compose.yml` が `required: false` を、見本が `!override` を使うため。`docker compose version` で確かめられます)
* amd64 または arm64 のホスト(ハードウェアエンコードの見本は amd64 のみ)
* mirakc を同梱で使う場合: チューナーとカードリーダー、mirakc の `config.yml`(チャンネルとチューナーの定義)

## セットアップ

[Setup.md](Setup.md) を参照してください。

## EDCB へのアクセス

主にブラウザから操作します。ポートは既定の場合です。

* EMWUI: 録画予約、録画の管理、視聴など  
  `http://<ホストのアドレス>:5510/E3/`(EMWUI 3。以前の `/EMWUI/` は上流で削除されました)  
  ライブ視聴(TS-Live!)などは HTTPS が必要です([Setup.md の「HTTPS」](Setup.md#https))
* Legacy WebUI: EDCB の設定、管理など  
  `http://<ホストのアドレス>:5510/legacy/`
* EpgTimerNW(Windows クライアント): TCP の 4510 番に接続します  
  tkntrec 版との互換のため、`CompatFlags=4095` を初回の起動時に書きます

## edcbctl

コンテナの中で、`docker compose exec edcb edcbctl <サブコマンド>` として使います。

| サブコマンド | 内容 |
|---|---|
| `status` | 録画中か、録画中の予約、次の予約を表示します。再起動や更新の前に確かめます |
| `backends` | 接続先ごとの状態、チューナー数、チャンネル定義の状態を表示します |
| `chscan <名前>…` / `chscan --all [--rebuild]` | チャンネルをスキャンし直します([Setup.md](Setup.md#チャンネル定義)) |
| `prune [--diff]` | 外した接続先などの、もう使わない設定を片付けます([Setup.md](Setup.md#接続先を外したとき)) |
| `allow-setting on\|off\|status` | Legacy WebUI からの設定変更の許可を、再起動せずに切り替えます |
| `provision --diff` | 起動時の設定処理が何を変えるかを、変えずに表示します |

## 更新

更新ではコンテナを作り直すので、**録画中に行うと録画が止まります。** 先に録画中でないこと、直近に予約が無いことを確かめます。

```sh
docker compose exec edcb edcbctl status
```

```
recording: no
next reservation: 2026-10-07 21:00 (in 5h 12m) 番組名 (放送局)
reservations: 12 enabled, 0 disabled
```

このリポジトリは、リリースごとにタグ(`v2.0.0` など)を付けます。**タグを指定して更新することを勧めます。**

```sh
git fetch --tags
git checkout v2.0.1          # 更新先のタグ
docker compose build
docker compose up -d
```

* `main` ブランチを追う(`git pull`)こともできますが、リリース前の変更が入ることがあります
* Watchtower などの自動更新ツールは使わないでください。録画中でもコンテナを作り直すため、録画が止まります
* `docker compose up -d` で作り直されるのは、定義やイメージが変わったコンテナだけです。止まっている間の録画は行われません
* 停止の要求を受けた EDCB は、録画中のファイルを閉じてから終わります(最大 2 分待ちます)

更新後は `docker compose logs edcb` で、起動時の警告(`WARNING`)が出ていないか確かめてください。

## 上流のバージョンとパッチ

上流のバージョンは `edcb/Dockerfile` と `mirakc/Dockerfile` の `ARG` の既定値で固定しています(タグとコミット、mirakc はイメージの版とダイジェスト)。新しいバージョンは CI が週に 1 回調べ、パッチ込みでビルドできれば、固定を更新する PR を作ります。

| 対象 | 固定のしかた |
|---|---|
| EDCB(`xtne6f/EDCB`) | `EDCB_REF`(`work-plus-s-*` のタグ)と `EDCB_COMMIT`。タグがそのコミットを指すことをビルド時に確かめます |
| BonDriver_LinuxMirakc | `BON_DRIVER_COMMIT` |
| EMWUI | `EMWUI_COMMIT` |
| Lua、lua-zlib | `LUA_COMMIT`、`LUA_ZLIB_COMMIT` |
| mirakc | `MIRAKC_VERSION` と `MIRAKC_DIGEST`(`mirakc/mirakc:<版>-debian`) |
| libaribb25 | `LIBARIBB25_COMMIT` |

別のバージョンでビルドしたい場合は、`compose.override.yml` の `build: args:` でこれらを指定します(パッチが当たらなければビルドは失敗します)。

### EDCB へのパッチ(`edcb/patches/edcb/`)

* `0001-write-default-prealloc-option.patch`  
  録画開始時の容量確保(fallocate)を、設定で止められるようにします。このイメージでは、btrfs 上では確保しないのが既定です
* `0002-free-folder-min-mb-option.patch`  
  別の録画フォルダへ切り替える基準の空き容量(上流は 200MB 固定)を設定できるようにします

設定方法は [Setup.md の「録画保存先が btrfs の場合」](Setup.md#録画保存先が-btrfs-の場合) を参照してください。

### BonDriver_LinuxMirakc へのパッチ(`edcb/patches/bondriver/`)

* `0001-Resolve-SERVER_HOST-on-every-connect.patch`  
  接続先にホスト名を使えるようにします。接続のたびに名前を引くので、相手のコンテナの IP アドレスが変わってもつながります
* `0002-Bound-the-copies-into-the-response-buffers.patch`  
  API の応答を固定長のバッファへ長さを確かめずにコピーしていたのを直します(チャンネルの多い構成で壊れないように)
* `0003-Reconnect-when-the-stream-is-closed-while-receiving.patch`  
  受信中に接続が切れたら、同じチャンネルへつなぎ直します。EDCB は受信が止まっても選局し直さないので、これが無いと mirakc の再起動などで、その録画が終わりまで空になります

## 開発者向け

* 検証: `scripts/check.sh`(Docker デーモン不要)と `tests/integration/run.sh`(Docker を使う結合テスト。[説明](tests/integration/README.md))
* v2 の設計資料: [docs/v2/](docs/v2/README.md)
