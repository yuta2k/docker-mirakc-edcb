# v1 から v2 への移行

v1(`compose-sample.yml` をもとに自分で `compose.yml` を作っていた版)から、v2 に移る手順です。

**EDCB の設定(`edcb/ini/`)とチャンネル定義は、そのまま使えます。** 録画予約や WebUI で行った設定も引き継がれます。v2 の初回の起動で、無かった設定が足されるだけです([初回の起動で足されるもの](#初回の起動で足されるもの))。

移行のあいだ、録画は止まります(作業 6 の停止から作業 9 の起動まで)。予約の無い時間に行ってください。

## 何が変わるか

* `compose.yml` をこのリポジトリで管理するようになりました。自分の環境の設定は `compose.override.yml` と `edcb.env` に書きます
* 手元に `compose.yml` があると、`git pull` が次のエラーで止まります。**消さずに、下の手順で退避してください。**

  ```
  error: The following untracked working tree files would be overwritten by merge:
          compose.yml
  ```

* コンテナ名とボリューム名を固定しなくなりました。コンテナ名は `edcb` から `<プロジェクト名>-edcb-1`(プロジェクト名は、既定ではフォルダの名前)に変わり、mirakc の EPG キャッシュは新しいボリュームに作り直されます
* EDCB は root ではなく、`PUID` / `PGID`(既定 `1000` / `1000`)のユーザで動きます。`user:` は使えません
* EDCB の取得元が tkntrec 版から xtne6f 版に変わりました。tkntrec 版の EpgTimerNW との互換のため、`CompatFlags=4095` を書きます
* 設定の多くを、起動時に自動で整えるようになりました(チューナー数、チャンネル定義、アクセス制御など)。既にある設定は変えません

## 対応表

| v1 | v2 |
|---|---|
| `compose.yml`(自分で作成) | `compose.yml`(リポジトリ管理。編集しない)+ `compose.override.yml`(自分の環境の差分) |
| `container_name: edcb` / `mirakc` | 書かない。`<プロジェクト名>-edcb-1` など。操作は `docker compose exec edcb ...` |
| ボリューム `mirakc_epg` | `<プロジェクト名>_mirakc-epg`(新しく作られる) |
| `user: 1000:1000` | `PUID=1000`、`PGID=1000`(`edcb.env` か `environment`)。未指定なら `1000` / `1000` |
| `group_add` | そのまま使える。`/dev/dri` 用の `video` などは不要(自動で引き継ぐ) |
| `environment: UMASK=002` | そのまま使える |
| `environment: MIRAKC_ADDRESS` / `MIRAKC_PORT` | `EDCB_BACKEND_DEFAULT_URL=http://<アドレス>:<ポート>`。v1 の変数も引き続き読む。同梱の mirakc なら何も書かない |
| `environment: TZ=Asia/Tokyo` | 不要(イメージの既定)。変えるなら `TZ` |
| mirakc の `devices: /dev/bus:/dev/bus` | **`/dev/bus/usb:/dev/bus/usb` を `compose.override.yml` に書く**(`compose.yml` には無い。書かないとスクランブル解除できない) |
| ビルド引数 `EDCB_CHECKOUT` | `EDCB_REF`(タグ)と `EDCB_COMMIT`(そのタグのコミット)。通常は指定しない |
| ビルド引数 `BON_DRIVER_CHECKOUT`、`EMWUI_CHECKOUT` | `BON_DRIVER_COMMIT`、`EMWUI_COMMIT`。通常は指定しない |
| ビルド引数 `EDCB_PREALLOC_DEFAULT` | そのまま使える |
| `chlegacyset.sh true` / `false` | `docker compose exec edcb edcbctl allow-setting on` / `off`。常に許可するなら `EDCB_LEGACY_ALLOW_SETTING=true` |
| tkntrec 版 EDCB | xtne6f 版 EDCB。`CompatFlags=4095`(`EDCB_COMPAT_FLAGS` で変えられる) |
| ポート `4510:4510`、`5510:5510` | `compose.yml` で公開済み。番号を変えていたなら `.env` の `EDCB_HOST_TCP_PORT` / `EDCB_HOST_HTTP_PORT` |
| EMWUI の `/EMWUI/` | `/E3/`(上流で変わった) |

## 手順

コマンドは、このリポジトリのフォルダで実行します。`edcb/ini` は root の所有になっていることが多いので、ファイルの操作には `sudo` を付けます。Docker の操作に root が必要な環境では、そちらにも `sudo` を付けてください。

### 1. 今の状態を控える

```sh
git rev-parse HEAD > v1-commit.txt     # 元に戻すときに使う
docker compose config > v1-config.txt  # 今の構成(書き写すときの見本)
ls -ln edcb/ini                        # 所有者の UID / GID を見る
```

`ls -ln` で、`edcb/ini` のファイルの所有者を確かめます。

* `0 0`(root): v1 で `user:` を指定していなかった。作業 7 で所有者を変えます
* `1000 1000` など: v1 で `user:` を指定していた。その番号を `PUID` / `PGID` に書きます

### 2. 退避する

```sh
mv compose.yml compose.yml.v1
sudo cp -a edcb/ini edcb/ini.v1-backup
```

`edcb/ini.v1-backup` は、元に戻すときに使います。録画ファイルは含みません。

v1 のイメージも、元に戻すときのために名前を付けておきます。

```sh
docker compose -f compose.yml.v1 images   # IMAGE の列の名前(例: docker-mirakc-edcb-edcb)
docker tag docker-mirakc-edcb-edcb edcb:v1-backup
docker tag docker-mirakc-edcb-mirakc mirakc:v1-backup
```

### 3. 更新する

```sh
git status            # 変更したファイルが無いか
git pull
git checkout v2.0.0   # 使うリリースのタグ
```

`git status` に、自分で変更したファイル(`edcb/Dockerfile` のハードウェアエンコードの部分など)が出た場合は、`git stash` で退避してから `git pull` します。v2 では Dockerfile を編集せずに済むようになっています(ハードウェアエンコードは [Setup.md の「ハードウェアエンコード」](../Setup.md#ハードウェアエンコードintel))。

### 4. compose.override.yml と edcb.env を作る

```sh
cp compose.override-sample.yml compose.override.yml
cp edcb.env-sample edcb.env
```

`compose.yml.v1` から、自分の環境の設定を書き写します([対応表](#対応表))。`compose.override.yml` には、`compose.yml` との差分だけを書きます。例:

```yaml
# compose.override.yml
services:
  mirakc:
    devices:
      - /dev/bus/usb:/dev/bus/usb   # カードリーダー(v1 の /dev/bus の代わり)
      - /dev/px4video0              # v1 で書いていたチューナー
      - /dev/px4video1
  edcb:
    volumes:
      - /mnt/recorded:/recorded     # v1 で書いていた録画先
```

```sh
# edcb.env(v1 の user: と environment から)
PUID=1000
PGID=1000
```

* `container_name`、ボリュームの `name: mirakc_epg`、`user:` は書き写しません
* ホストの pcscd を使う構成にする場合は、[Setup.md の「pcscd」](../Setup.md#pcscd) を参照してください

書けたら、内容を確かめます。

```sh
docker compose config
```

`v1-config.txt` と比べて、チューナー、録画先、ポートが同じになっていることを確かめます。

### 5. ビルドする

```sh
docker compose build
```

ビルドの間も、v1 のコンテナは動き続けます。

### 6. v1 のコンテナを止めて削除する

録画中でないことを、WebUI で確かめてから行います。

```sh
docker compose -f compose.yml.v1 down
```

**v2 を起動する前に、必ず行ってください。** v1 のコンテナ(`edcb`、`mirakc`)は名前が違うので、v2 の起動では消えません。残っていると、ポートとチューナーを取り合います。

### 7. 所有者を合わせる(root で動かしていた場合)

作業 1 で所有者が root だった場合は、`PUID` / `PGID` のユーザに変えます。

```sh
sudo chown -R 1000:1000 edcb/ini
sudo chown -R 1000:1000 /mnt/recorded   # 録画先(compose.override.yml の volumes)
```

録画先をほかのソフトウェアと共有していて所有者を変えたくない場合は、グループで書き込めるようにして、そのグループを `PGID` か `group_add` で渡します。

### 8. 起動する

```sh
docker compose up -d
docker compose logs edcb | grep -E 'provision|entrypoint'
```

ログで次を確かめます。

* `WARNING: not writable by PUID=...` が出ていない(出たら作業 7)
* `provision:` の行で、足された設定(下の [初回の起動で足されるもの](#初回の起動で足されるもの))
* `docker compose logs mirakc` に、カードリーダーの USB についての警告が出ていない

### 9. 動作を確かめる

* `http://<ホストのアドレス>:5510/E3/` と `/legacy/` が開ける
* 番組表と予約が残っている
* `docker compose exec edcb edcbctl backends` で、チューナー数とチャンネル定義の状態を見る
* `docker compose exec edcb edcbctl status` で、予約が見える

### 10. 片付ける

動作を確かめたら、v1 のものを片付けます。

```sh
docker volume rm mirakc_epg                 # v1 の mirakc の EPG キャッシュ
docker image rm edcb:v1-backup mirakc:v1-backup
rm compose.yml.v1 v1-config.txt v1-commit.txt
sudo rm -rf edcb/ini.v1-backup
```

`edcb/ini/` に残る次のものは、v2 では使いません。消してもかまいません。

* `HttpPublic/EMWUI/`: 上流で削除された旧 EMWUI(新しい EMWUI は `HttpPublic/E3/`)
* `*.fifo`: 起動のたびに消します

## 初回の起動で足されるもの

既にあるキーは変えません。足されるのは、無かったキーだけです(v1 の利用者の実際の設定で確かめています)。

* `EpgTimerSrv.ini [SET]`: `HttpNumThreads=50`、`EnableTCPSrv=1`、`TCPAccessControlList`(localhost とプライベートアドレス帯)、`CompatFlags=4095`。`HttpAccessControlList` も、無ければ同じ範囲で書きます
* `EpgDataCap_Bon.ini [SET_TCP]`: リモート視聴用の送信先(SrvPipe)
* `EpgTimerSrv.ini [TVTEST]`: 視聴に使う BonDriver の一覧が無ければ、チューナーのある BonDriver
* `[BonDriver_LinuxMirakc*.so]`: セクションが無い種類だけ、チューナー数

注意する点:

* **TCP サーバ(4510)が有効になります**(`EnableTCPSrv` が無かった場合)。接続できるのは、localhost とプライベートアドレス帯だけです。使わない場合は `EDCB_TCP_ENABLE=false`
* **Legacy WebUI からの設定変更は禁止に戻ります。** `chlegacyset.sh true` で許可していた場合も同じです。`edcbctl allow-setting on` で許可します
* `edcb/ini/HttpPublic/` のファイルは、イメージに合わせて入れ替わります。内容が違うファイルは、`edcb/ini/.provision/backup/` に退避してから置き換えます
* 変更前の ini は `edcb/ini/.provision/backup/` に退避します

### チャンネル定義

v1 で作ったチャンネル定義(`Setting/ChSet5.txt`、`Setting/*.ChSet4.txt`)は、そのまま使います。`ChSet5.txt` があるので、自動のスキャンは行いません。

v1 のチャンネル定義は「自分で置いたもの」として扱い、上書きも削除もしません。地上波用 / 衛星用への自動の分割も行いません。自動で作ったものに切り替えたい場合は、`--force` を付けてスキャンします(元のファイルは退避します)。

```sh
docker compose exec edcb edcbctl chscan DEFAULT --force
docker compose restart edcb   # 録画中でないことを確かめてから
```

`ChSet5.txt` で変えた EPG 取得対象・検索対象の設定は引き継ぎます。

## コンテナ名で操作していた場合

`docker exec edcb ...` のように、コンテナ名で操作するスクリプトや cron は、名前が変わるので動かなくなります。サービス名で操作するように直してください。

```sh
# v1
docker exec edcb EpgDataCap_Bon -h
# v2(このリポジトリのフォルダで)
docker compose exec edcb EpgDataCap_Bon -h
# v2(ほかのフォルダから)
docker compose --project-directory /path/to/docker-mirakc-edcb exec edcb EpgDataCap_Bon -h
```

ほかのコンテナから `edcb` や `mirakc` というホスト名でつないでいた場合は、Compose のネットワークの中ではサービス名で引けるので、同じプロジェクトの中なら変わりません。別のプロジェクトからつないでいた場合は、ホストのアドレスとポートでつなぐように直してください。

## 元に戻す

v2 で問題があった場合は、次の手順で v1 に戻せます。**移行のあとに追加・変更した予約と設定は失われます。**

```sh
docker compose down
mv compose.override.yml compose.override.yml.v2   # v1 の compose.yml に重ならないように
mv edcb.env edcb.env.v2
git checkout "$(cat v1-commit.txt)"
mv compose.yml.v1 compose.yml
sudo mv edcb/ini edcb/ini.v2
sudo cp -a edcb/ini.v1-backup edcb/ini
docker tag edcb:v1-backup docker-mirakc-edcb-edcb       # 作業 2 で控えた名前
docker tag mirakc:v1-backup docker-mirakc-edcb-mirakc
docker compose up -d --no-build
```

作業 7 で録画先の所有者を変えた場合は、必要に応じて戻してください。v1 の最後のリリースタグは `v1.0.4` です。
