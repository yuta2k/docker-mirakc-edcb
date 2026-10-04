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
- `container_name` と、ボリュームの `name:` を書かない(`decisions.md` の D5)。
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

- [x] `docker build edcb/` が、引数なしで成功する
- [x] ビルドログで、EDCB が `EDCB_COMMIT` のコミットであること、パッチ 2 本が当たったことが確認できる
- [x] `EDCB_COMMIT` をわざと別の値にすると、ビルドが失敗する
- [x] パッチをわざと壊すと、ビルドが失敗する
- [x] ビルドしたイメージを一時ディレクトリの構成で起動し、`/legacy/` と `/EMWUI/` が HTTP 200 を返す(U2)。ACL は一時構成の `EpgTimerSrv.ini` で調整する
  - `/EMWUI/` は上流で `/E3/` に変わったため、`/E3/` で確認した(実施記録を参照)
- [x] `docker compose config` が、`compose.yml` 単体でも、`compose.override-sample.yml` を override として重ねても成功する
- [x] `docker compose config` の結果に、固定のコンテナ名とボリューム名が現れない。`COMPOSE_PROJECT_NAME` を変えると、コンテナ名とボリューム名がそれに従って変わる
- [x] 3 つのワークフローが `actionlint`(使えれば)を通る

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

2026-10-04〜05 実施。作業ブランチ `v2-phase-1-build`。

### 行ったこと

**上流の固定(`edcb/Dockerfile`、`mirakc/Dockerfile`)**

- EDCB の取得元を `xtne6f/EDCB` に変えた。ARG の既定値(Dockerfile 冒頭)だけで固定している。
  - `EDCB_REPO` / `EDCB_REF` / `EDCB_COMMIT`
  - `BON_DRIVER_REPO` / `BON_DRIVER_COMMIT`
  - `EMWUI_REPO` / `EMWUI_COMMIT`
  - `LUA_REPO` / `LUA_COMMIT`、`LUA_ZLIB_REPO` / `LUA_ZLIB_COMMIT`(ブランチの tarball をやめて、コミットで固定)
- 取得は `edcb/build/fetch-source.sh` にまとめた。`git fetch --depth 1` で ref(タグ)かコミットを取り、`git rev-parse HEAD` が `*_COMMIT` と一致しなければ失敗する。`*_COMMIT` は 40 桁の SHA-1 でないと失敗する。サブモジュール(BonDriver の picojson)は、記録されたコミットで取る。
- 最終イメージに、上流のバージョンをラベルとして入れた(`io.github.yuta2k.docker-mirakc-edcb.{edcb,bondriver,emwui}.{repo,ref,commit}`)。
- `mirakc/Dockerfile` の libaribb25 を `LIBARIBB25_REPO` / `LIBARIBB25_COMMIT` で固定した。ほかは変えていない。
- 廃止したビルド引数: `EDCB_CHECKOUT`、`BON_DRIVER_CHECKOUT`、`EMWUI_CHECKOUT`。指定されても Docker の警告が出るだけで、無視される。Readme に、廃止したことと代わりの引数を書いた。

**パッチ**

- `edcb/patches/*.patch` を `edcb/patches/edcb/` に移した。
- `git -c user.name=... -c user.email=... am --3way --keep-cr` で当てる。パッチが 1 つも無ければ失敗する。当てたあとに `git log --oneline <EDCB_COMMIT>..HEAD` をログに出す。
- `--keep-cr` が必要(EDCB のソースは CRLF。`facts.md` の F1 に追記)。
- `EDCB_PREALLOC_DEFAULT` と `CPPFLAGS` はそのまま。

**compose**

- git 管理する `compose.yml` と `compose.override-sample.yml` を作り、`compose-sample.yml` を削除した。
  - `container_name` とボリュームの `name:` は書いていない。
  - 環境変数は従来どおり(`MIRAKC_ADDRESS` / `MIRAKC_PORT`)。`env_file`、`overrides` のマウント、ポートの追加はしていない。
  - `design.md` の 2 章から、仕様を変えない範囲で次を先に入れた: `depends_on` の `required: false`、`mirakc/config.yml` の長い書式のマウント(`create_host_path: false`)。
  - `user:`、`group_add`、`/dev/dri`、ビルド引数、mirakc の無効化、外部 mirakc の例は `compose.override-sample.yml` に置いた。
- `.gitignore`: `compose.yml` を外し、`compose.override.yml`、`edcb.env`、`edcb/overrides/*`、`compose.yml.v1-backup` を追加した。
- 利用者の未追跡の `compose.yml` の扱いはユーザに確認した。答えは「override に書き換えて移す」。
  - 元のファイルは `compose.yml.v1-backup` として残した(git 管理外)。
  - 差分だけの `compose.override.yml` を作った(`ports: !override` など)。
  - `docker compose config` で、新旧の実効の構成を比べた。違いは意図した 3 点だけ: `required: false`、`create_host_path: false`、`driver: local` の省略(既定値なので同じ意味)。
  - 利用者の構成を変えないよう、override には旧来の `container_name` とボリューム名 `mirakc_epg` を残した。削除を勧めることはユーザに伝えた。

**CI(`.github/workflows/`)**

- `.github/scripts/smoke-test.sh`: `EpgTimerSrv -h` / `EpgDataCap_Bon -h` を実行する(終了コード 2 と `Ver.` の表示を成功とみなす)。あわせて、上流のバージョンのラベルを表示する。3 つのワークフローで共用する。
- `build.yml`: PR と `main` / `v2` への push、手動実行で動く。
  - edcb は amd64 と arm64 の両方をビルドし、スモークテストを行う。arm64 は QEMU ではなくネイティブランナー(`ubuntu-24.04-arm`、public リポジトリは無料)を使う。U1 を確かめるため。
  - mirakc は amd64 のビルドだけ。libaribb25 の固定を確かめるため。
- `release.yml`: `v*` タグで動く。
  - amd64 / arm64 をそれぞれのネイティブランナーでビルドし、スモークテストを通してから digest で push する。そのあと、マニフェストリストにまとめる。
  - タグは `<バージョン>`、`<メジャー.マイナー>`、`latest`(metadata-action の既定で、プレリリースには付かない)。
  - イメージ名は `ghcr.io/<owner>/<repo>/edcb`(このリポジトリなら `ghcr.io/yuta2k/docker-mirakc-edcb/edcb`)。
- `upstream-check.yml`: 毎週月曜 03:00 JST と手動実行で動く。
  - `git ls-remote` で `work-plus-s-*` の最新タグを調べる(注釈付きタグなら `^{}` のコミットを使う)。
  - 新しければ `EDCB_REF` / `EDCB_COMMIT` を書き換えて、amd64 のビルドとスモークテストを行う。成功したら PR を、失敗したら Issue を作る(同じタイトルの Issue が開いていればコメントを足す)。
  - ブランチ `upstream/edcb-<タグ>` が既にあれば何もしない。
  - トークンは、`UPSTREAM_CHECK_TOKEN` シークレットがあればそれを、無ければ `GITHUB_TOKEN` を使う。

**ドキュメント(最小限)**

- Readme:
  - EDCB のリンクを xtne6f 版に変えた。
  - 更新方法とパッチの節を、固定方式に合わせて直した。廃止したビルド引数の案内も書いた。
  - EMWUI の URL を `/E3/` に直した。
- Setup.md:
  - `compose-sample.yml` を `compose.override-sample.yml` / `compose.override.yml` に直した。
  - 同じ名前のフォルダの構成を 2 つ置く場合の `COMPOSE_PROJECT_NAME` の注意を書いた。
  - パッチのパスを直した。
- `facts.md`: 固定値(lua、lua-zlib、libaribb25 を追加)、F1(`--keep-cr`、`-h`)、F6(E3)、U1、U2、U8 を更新した。
- `phases/2-provision.md`: HTTPS の確認手順の URL を `/E3/` に直した。

### 検証結果

Docker デーモンが要る確認は、ユーザに sudo でスクリプトを実行してもらい、ログを読んで判断した(Docker 29.8.1、Compose 5.5.1)。

| 確認 | 結果 |
|---|---|
| `docker build edcb/`(引数なし) | 成功 |
| ビルドログ | `Fetched https://github.com/xtne6f/EDCB.git work-plus-s-260904 at ebf50c73…`、`Applying:` が 2 行、`Applied 2 patch(es) on top of ebf50c73…` に続いて 2 コミットが表示された |
| `EDCB_COMMIT=f0a082f…`(別のタグのコミット) | 失敗(rc=1)。`ERROR: … work-plus-s-260904 is at ebf50c7…, expected f0a082f…` |
| パッチ 0002 の文脈行を壊す | 失敗。`git am` が `patch does not apply` で exit 128 |
| スモークテスト | 両方 `Ver. work+s-260904`、終了コード 2。ラベル 7 つを確認 |
| 一時構成で起動(`-p 127.0.0.1:15510:5510`、ACL を `+0.0.0.0/0` に変えて再起動) | `/` 200、`/legacy/` 200、`/E3/` 200、`/E3/index.html` 200、`/EMWUI/` 404 |
| `docker compose config`(`compose.yml` 単体 / sample を重ねる) | どちらも成功。出力に `container_name` は無い |
| `COMPOSE_PROJECT_NAME` を変える | `config` で、ボリュームとネットワークが `proja_mirakc-epg` / `projb_mirakc-epg` のように変わる。`docker compose --dry-run create` で、コンテナ名が `edcbtest-a-edcb-1` / `edcbtest-b-edcb-1` になることを確認。ドライランでは何も作られていないことも確認した |
| `docker build mirakc/` | 成功(`Fetched …libaribb25.git at dc1d96a…`) |
| actionlint 1.7.12(shellcheck 0.11.0 と組み合わせて実行) | 3 ファイルともエラー 0。`fetch-source.sh` と `smoke-test.sh` も shellcheck を通る |
| CI(PR #15、`build.yml`) | `edcb (amd64)`、`edcb (arm64)`、`mirakc` がすべて通った。arm64 のログに `Architecture: aarch64`、`Applied 2 patch(es)`、`Ver. work+s-260904` がある |
| U8(フェーズ 2 の先取り) | `libssl.so.3`、`libcrypto.so.3` がある |

### 満たせなかった・読み替えた条件

- **`/EMWUI/` → `/E3/`**: EMWUI は 2026-07-17 に旧 `EMWUI/` を削除し、E3(EMWUI 3)に移行していた(`facts.md` の F6)。固定したコミットにも `/EMWUI/` は無いので、`/E3/` で確認した。上流の構成の変化であり、今回の変更が原因ではない。
- **U1(arm64)**: このホストには QEMU の binfmt が無い。ホスト全体に効く設定なので入れず、ローカルでは確認しなかった。PR #15 の CI(`build.yml`)で確認した。ネイティブ arm64 ランナー(aarch64)で、固定コミットの取得、パッチ 2 本の適用、ビルド、スモークテスト(`Ver. work+s-260904`、終了コード 2)が通った。`release.yml` は amd64 / arm64 のままにする。

### 設計から変えた点・実装時に決めた点

- `compose.yml` に `image:`(GHCR)を書いていない。まだ公開していないので、書くと pull のエラーになる。公開の判断が済んだフェーズで足す。
- release のイメージ名を `ghcr.io/<owner>/<repo>/edcb` にした(設計では未指定)。
- `build.yml` に arm64 と mirakc のジョブを足した(設計では amd64 の edcb のみ)。
- libaribb25 は浅い取得のため、`git describe --always --tags` によるバージョン文字列が、タグ名ではなく短いハッシュになる。動作には影響しない。

### レビューでの修正

`/code-review` の指摘を受けて、次の 3 点を直した。

- Readme の更新方法に、手元に `compose.yml` がある v1 の利用者向けの移行手順を足した。`git pull` が未追跡の `compose.yml` で止まるので、退避してから `compose.override.yml` に書き写す。フェーズ 6 の移行案内は、これを土台にして書き直すこと。
- `release.yml` のトリガーを semver のタグ(`v[0-9]+.[0-9]+.[0-9]+*`)に絞った。あわせて、イメージのタグが空なら push の前に失敗させるようにした。
- `upstream-check.yml` の Issue 本文で、ビルドログを囲む記号を `~~~~~~~~` に変えた(ログに ```` ``` ```` があっても崩れない)。

### 次のフェーズへの申し送り

- **CompatFlags**: xtne6f 版は `[SET] CompatFlags` を読み、既定値は 0。フェーズ 2 で `CompatFlags=4095` の既定値を書くまでは、tkntrec 版の EpgTimerNW との互換が失われる。v2 は全フェーズを入れてから出すので、利用者への影響は無い。ただし、この開発環境でフェーズ 1 のイメージを使うときは注意。
- **E3**:
  - EMWUI の `Setting/`(`HttpPublic.ini`、`XCODE_OPTIONS.lua`)の置き場所は従来どおり。`api/util.lua` の `ALLOW_SETTING` / `ALLOW_SETTING_LIST` も E3 で変わっていない。
  - 既存のボリュームには旧 `HttpPublic/EMWUI/` が残る。フェーズ 2 で `HttpPublic` をイメージ側へ移すときの案内(6 章)に含めること。
  - README の推奨設定や SSE 用ポートの記述は E3 の README に基づいている。
- **U3**: EMWUI の Lua はボリュームの `HttpPublic/api/` 以下にある(`xcode`、`view`、`Settings` など)。書き込み先の調査対象に含めること。`api/Settings` は `Setting/HttpPublic.ini` に `WritePrivateProfile` で書く。
- **スモークテスト**: フェーズ 2 で pytest を足すときは `build.yml` の edcb ジョブに追加する。`smoke-test.sh` は、ラベルが 1 つも無いと失敗する。
- **定期チェックを有効にする前に**: 自動 PR で CI を動かすには、`UPSTREAM_CHECK_TOKEN`(contents / pull-requests の書き込み権限)を登録する必要がある(README の「ユーザの作業が必要なもの」)。定期実行は、このワークフローが既定ブランチ(`main`)に入るまで動かない。
- **この開発環境**: `compose.override.yml` に旧来の `container_name`(`edcb-4ts`、`mirakc`)とボリューム名 `mirakc_epg` を残している。D5 の確認をこの環境でするなら、これらを消すこと。次に `up` すると、構成が変わったためコンテナが作り直される。

