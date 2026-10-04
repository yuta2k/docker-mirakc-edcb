# フェーズ 1: ビルド基盤

## 目的

上流のバージョンを固定し、パッチの適用を堅くし、CI で検証できるようにする。あわせて `compose.yml` を git 管理に入れる。**コンテナの実行時の動作は、このフェーズでは変えない**(entrypoint は現状のまま)。

関連する方針: `decisions.md` の A1〜A4、D4。仕様: `design.md` の 1、2 章。

## 作業

### 1. EDCB の取得元と固定

- `edcb/Dockerfile` の EDCB の取得元を `xtne6f/EDCB` に変える。
- ARG を次のように定義し、既定値を `facts.md` の「固定に使う値」にする。
  - `EDCB_REPO`(既定 `https://github.com/xtne6f/EDCB.git`)
  - `EDCB_REF`(タグ)と `EDCB_COMMIT`(コミット)
  - `BON_DRIVER_REPO` と `BON_DRIVER_COMMIT`
  - `EMWUI_REPO` と `EMWUI_COMMIT`
- 取得後に `git rev-parse HEAD` が `*_COMMIT` と一致することを検査し、違えばビルドを失敗させる。
- 既存の `EDCB_CHECKOUT`、`BON_DRIVER_CHECKOUT`、`EMWUI_CHECKOUT` は廃止する(README の移行案内に書く材料として、実施記録に残す)。
- Lua 関連(`xtne6f/lua`、`xtne6f/lua-zlib`)はブランチの tarball を取っている。これもコミットで固定する。

### 2. パッチ

- `edcb/patches/*.patch` を `edcb/patches/edcb/` に移す。
- `git apply` を `git am --3way` に変える。コミッタ情報が要るので `git -c user.name=... -c user.email=...` を付ける。
- 失敗したらビルドが失敗すること。
- `EDCB_PREALLOC_DEFAULT` のビルド引数と `CPPFLAGS` の指定は維持する。

### 3. compose

- `compose-sample.yml` をもとに、git 管理する `compose.yml` と `compose.override-sample.yml` を作る(`design.md` の 2 章)。`compose-sample.yml` は削除する。
- **このフェーズでは環境変数の仕様は変えない。** `MIRAKC_ADDRESS` / `MIRAKC_PORT` は `compose.yml` に残す。`env_file`、`overrides` のマウント、ポートの追加はフェーズ 2 以降で足す。
- `user:` の例は `compose.override-sample.yml` に移す(フェーズ 2 で PUID / PGID に置き換える)。
- `.gitignore` を更新する。
- 利用者の未追跡の `compose.yml` が作業ツリーにある。**上書きも削除もしない。** 新しい `compose.yml` を置く前に、既存のものを `compose.override.yml` へ移してよいかユーザに確認する。確認が取れるまでは、新しいファイルを別名(`compose.v2.yml`)で作って作業を進めてよい。

### 4. CI(`.github/workflows/`)

- `build.yml`: PR と `v2` / `main` への push で、edcb イメージをビルドする(amd64)。ビルドしたイメージで `EpgTimerSrv -h` と `EpgDataCap_Bon -h` が動くことを確認する。フェーズ 2 以降で pytest をここに足す。
- `release.yml`: `v*` タグの push で、マルチアーキテクチャ(amd64 / arm64)のイメージをビルドし、GHCR へ push する。タグは `<バージョン>`、`<メジャー.マイナー>`、`latest`。上流のバージョンは OCI ラベルに入れる。**ワークフローを書くだけで、タグの作成や公開はしない。**
- `upstream-check.yml`: 週 1 回と手動実行。xtne6f の最新リリースタグを調べ、固定より新しければ Dockerfile の ARG を書き換えてビルドする。成功したら PR を作り、失敗したら Issue を作る。PR を作る前にワークフロー内でビルドを済ませること(標準トークンで作った PR は CI を起動しないため)。
- arm64 でビルドできるか(U1)を確認する。できなければ `release.yml` を amd64 のみにして報告する。

### 5. mirakc イメージ

- `mirakc/Dockerfile` の libaribb25 の取得もコミットで固定する。ほかは変えない。

## 触らないもの

- `edcb/entrypoint.sh` の動作(ファイルの移動だけは可)
- `edcb/Dockerfile` のコメントアウト部分(Intel Media Driver と QSVEncC)。フェーズ 5 で見本に置き換えるまで残す
- `Readme.md` / `Setup.md` の全面的な書き直し(フェーズ 6)。このフェーズで変わった箇所の最小限の修正だけ行う

## 受け入れ条件

- [ ] `docker build edcb/` が、引数なしで成功する
- [ ] ビルドログで、EDCB が `EDCB_COMMIT` のコミットであること、パッチ 2 本が当たったことが確認できる
- [ ] `EDCB_COMMIT` をわざと別の値にすると、ビルドが失敗する
- [ ] パッチをわざと壊すと、ビルドが失敗する
- [ ] ビルドしたイメージを一時ディレクトリの構成で起動し、`/legacy/` と `/EMWUI/` が HTTP 200 を返す(U2)。ACL は一時構成の `EpgTimerSrv.ini` で調整する
- [ ] `docker compose config` が、`compose.yml` 単体でも、`compose.override-sample.yml` を override として重ねても成功する
- [ ] 3 つのワークフローが `actionlint`(使えれば)を通る

## 検証

```sh
# ビルド
docker build -t edcb:v2test edcb/

# 一時構成での起動(リポジトリ直下の構成を使わない)
tmp=$(mktemp -d); mkdir -p "$tmp/ini"
docker run -d --name edcbtest -p 15510:5510 -v "$tmp/ini:/var/local/edcb" \
  -e MIRAKC_ADDRESS=127.0.0.1 -e MIRAKC_PORT=40772 edcb:v2test
# ACL を調整して再起動し、curl で確認する。終わったら必ず削除する
docker rm -f edcbtest
```

## 実機確認の依頼

なし。

## 実施記録

(着手したエージェントが、行ったこと、設計から変えた点、次のフェーズへの申し送りを書く)
