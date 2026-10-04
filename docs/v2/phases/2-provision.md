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

- [ ] 空のディレクトリを `/var/local/edcb` にマウントして起動すると、`design.md` の 3.1 の既定値が書かれた状態で EpgTimerSrv が動く
- [ ] 同じ構成で再起動しても、ini が変化しない(変更内容の表示が「変更なし」になる)
- [ ] **既存の利用者のデータを模した ini**(現在の `edcb/ini/` の `*.ini` を一時ディレクトリにコピーしたもの)で起動すると、既にあるキーの値は 1 つも変わらない。追加されるのは、無かったキーだけ
- [ ] WebUI 相当の変更(ini のキーを手で書き換える)をしてから再起動しても、環境変数と上書き用 ini で指定していないキーは元に戻らない
- [ ] 値が `0` や空文字のキー(WebUI でオフにした状態)は「存在する」と扱われ、既定値で上書きされない(`SaveLogo=0`、`[SET_TCP] Count=0`、`EnableTCPSrv=0` で確認)
- [ ] 環境変数で指定したキーは、手で書き換えても再起動で戻る
- [ ] `edcbctl allow-setting on` の直後から、コンテナを再起動せずに Legacy WebUI の設定ページで保存できる。`off` の直後から保存が拒否される(設定ページへの POST の応答で確認)
- [ ] 許可した状態でコンテナを再起動すると、`EDCB_LEGACY_ALLOW_SETTING` の値(未指定なら禁止)に戻る
- [ ] `legacy/util.lua` の置き換え対象の行が無い状態を作ると、イメージのビルドが失敗する
- [ ] `group_add` で渡したグループと、`/dev/dri/renderD*` の所有グループ(存在する場合)が、権限を落としたあとのプロセスに残る
- [ ] 上書き用 ini に書いたキーが反映される。コメントや、ほかのキーの並びは変わらない
- [ ] 書き換えの前に退避が作られ、`--diff` では何も書き換わらない
- [ ] `PUID=1234 PGID=1234` で起動すると、EpgTimerSrv のプロセスと、新しく作られるファイルの所有者が 1234 になる
- [ ] `user: 1000:1000` を付けて起動すると、移行方法を示すメッセージを出して終了する
- [ ] 接続先に届かない状態でも、EpgTimerSrv が起動する
- [ ] `docker stop` で、EpgTimerSrv と子プロセスが残らずに終了する
- [ ] ヘルスチェックが healthy になる。`EnableHttpSrv=0` にしても unhealthy にならない
- [ ] pytest がすべて通る

## 検証

フェーズ 1 と同じく、一時ディレクトリと別のコンテナ名・ポートで行う。既存データの確認には、`edcb/ini/` を**コピー**して使う(元は書き換えない)。

```sh
tmp=$(mktemp -d); cp -a edcb/ini/*.ini "$tmp/"   # ini だけコピーする。Setting/ は大きいので必要な分だけ
```

## 実機確認の依頼

- HTTPS: `ssl_cert.pem` を置いて起動し、`https://<ホスト>:5511/EMWUI/` でライブ視聴(TS-Live!)ができるか。手順をまとめてユーザに依頼する。

## 実施記録

(着手したエージェントが書く)
