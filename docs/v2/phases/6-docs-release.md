# フェーズ 6: ドキュメントとリリース準備

## 目的

`Readme.md` と `Setup.md` を v2 の内容に書き直し、既存の利用者向けの移行手順を用意する。リリースできる状態にする(リリースそのものはユーザが行う)。

関連する方針: `decisions.md` の D3、D4、E2。

## 先に行うこと

フェーズ 1〜5 の「実施記録」をすべて読み、設計から変わった点と申し送りを反映する。`design.md` が実装と食い違っていれば、`design.md` を実装に合わせて直す。

## 作業

### 1. Readme.md

冒頭に **v1 からの移行**への導線を置く(`git pull` が未追跡の `compose.yml` で止まる利用者が、最初に読む場所になる)。

載せる内容:

- 構成の概要(同梱するもの、しないもの)
- 最短のセットアップ手順へのリンク
- 更新方法。固定タグでの利用を勧め、`latest` と自動更新ツールの併用は録画を中断するおそれがあると書く。更新前に `edcbctl status` で確認する手順
- 上流のバージョンと、当てているパッチの説明
- 必要な Docker Compose のバージョン(`!override`、`required: false` を使うため。実際に必要な版を調べて書く)

### 2. Setup.md

手順を、実際に空の状態から通して確認しながら書く(チューナーが要る部分は、ユーザの実機確認の結果を反映する)。

- 事前準備、`compose.override.yml` と `edcb.env` の作り方
- 環境変数の一覧(`design.md` の 3 章をもとに、利用者向けに書き直す)
- 上書き用 ini の使い方と、WebUI での設定との関係(上書き対象のキーは再起動で戻る、など)
- 複数の接続先の設定例。共有バックエンドではチューナー数を少なめに上書きすること、mirakc 側で専用チューナーを先に書くこと
- チャンネル定義: 初回の自動スキャン、再スキャン、ずれの警告が出たときの対処、手書きの定義を使う方法
- HTTPS の有効化(証明書の置き場所、EMWUI のライブ視聴に必要な理由)
- pcscd の 2 通りの構成と選び方
- ポートの公開範囲(Docker が公開したポートはホストのファイアウォール設定を通らない。LAN 側のアドレスに限定する書き方)
- 同じホストに構成を 2 つ置く場合の注意(フォルダ名が同じだとプロジェクト名が衝突し、片方の `up` / `down` がもう片方のコンテナに作用する。`.env` の `COMPOSE_PROJECT_NAME` とポートを変える)
- btrfs の節は現在の内容を維持し、変わった点だけ直す
- KonomiTV をつなぐ場合の例(同梱はしない。動作保証はしないと明記)

### 3. 移行手順(`docs/migration-v1-to-v2.md`)

- pull の前に `compose.yml` を退避する手順と、`compose.override.yml` への書き直し方
- 廃止・変更された指定の対応表(`user:` → `PUID` / `PGID`、`*_CHECKOUT` → 新しい ARG、`chlegacyset.sh` → 環境変数、tkntrec 版 → xtne6f 版と `CompatFlags`)
- コンテナ名とボリューム名が変わること(`decisions.md` の D5)。`docker exec edcb ...` のようにコンテナ名で操作している利用者への案内、古い `edcb` / `mirakc` コンテナの消し方(新しい構成で `up` する前に、古い `compose.yml` で `down` する)、不要になる `mirakc_epg` ボリュームの消し方
- 既存の設定とチャンネル定義はそのまま使えること、初回起動で追加されるキー
- 不要になるもの(ボリューム内の `HttpPublic/` など。フェーズ 2 の結果による)
- 元に戻す方法(退避の場所、v1 のタグ)

### 4. 仕上げ

- `docs/v2/` は開発用の資料として残す。`docs/v2/README.md` の状態表を「完了」にする。
- リポジトリ直下の `CLAUDE.md` から「進行中の作業」の節を外し、恒常的な内容(構成、検証の方法、守ること)に書き直す。

## 行わないこと

- タグの作成、GHCR への公開、`v2` ブランチの `main` へのマージ。**ユーザが行う。**
- 公開の判断に必要な材料(`facts.md` の F8 のライセンスの状況、公開の手順)を実施記録にまとめ、ユーザに渡す。

## 受け入れ条件

- [ ] `Setup.md` の手順を、空の一時ディレクトリで最初から実行して、チューナーが要らない範囲がすべて通る
- [ ] ドキュメントに出てくる環境変数、コマンド、ファイル名が、実装と一致する(1 つずつ突き合わせる)
- [ ] 移行手順を、v1 の構成を模した一時ディレクトリ(現在の `compose-sample.yml` 相当の `compose.yml` と、`edcb/ini/` のコピー)で実行して通る
- [ ] ドキュメント内のリンクが切れていない

## 実施記録

2026-10-06 着手。作業ブランチ `v2-phase-6-docs-release`(`v2` から作成)。

### 先に行ったこと

- フェーズ 1〜5 の実施記録を読み、申し送りを反映した(下の表)。
- `design.md` と実装の食い違いは 1 点だけだった。2 章の「`image:` に GHCR のイメージ」は、公開を決めていないので `compose.yml` に書いていない(フェーズ 1 の判断のまま)。`design.md` にその旨を書き足した。

| 申し送り | 反映先 |
|---|---|
| v1 の `compose.yml` の退避と `compose.override.yml` への書き直し(フェーズ 1) | 移行手順の作業 1〜4 |
| `user:` → `PUID` / `PGID`、`chlegacyset.sh` の廃止、許可が禁止に戻る、`HttpPublic` の退避と置き換え、旧 `HttpPublic/EMWUI/`、TCP サーバが有効になる、`MIRAKC_*` の移し先(フェーズ 2) | 移行手順の対応表と「初回の起動で足されるもの」 |
| mirakc の `config.yml` で専用チューナーを先に書く、`edcbctl status` を更新前の確認に(フェーズ 4) | Setup.md の「mirakc の設定」「チューナー数」、Readme の「更新」 |
| `/dev/bus/usb` を必ず案内、ホストの pcscd、`DISABLE_PCSCD`(フェーズ 5) | 移行手順の対応表と作業 4、Setup.md の「pcscd」 |
| ハードウェアエンコードの見本の使い方(フェーズ 5) | Setup.md の「ハードウェアエンコード(Intel)」 |
| `edcbctl prune`(フェーズ 5) | Readme の `edcbctl` の表、Setup.md の「接続先を外したとき」 |
| `compose.override-sample.yml` の `MIRAKC_ADDRESS` の案内(フェーズ 5) | `EDCB_BACKEND_DEFAULT_URL` に直した |

### 行ったこと

- `Readme.md`: 冒頭に v1 からの移行への導線。構成(同梱する・しないもの)、対応する接続先、必要な Docker Compose の版、`edcbctl` の一覧、更新方法(タグを指定する。自動更新ツールを使わない。`edcbctl status` で確かめる)、上流のバージョンの固定のしかたと、EDCB と BonDriver へのパッチの説明。
- `Setup.md`: 全面的に書き直した。最短の手順、事前準備、mirakc の設定、`compose.override.yml`、`edcb.env`、実行ユーザ、ポートの公開(ファイアウォールを通らないこと、`.env` でアドレスを付ける書き方)、起動と初回の自動処理、初回に書かれる設定、環境変数の一覧(`design.md` の 3 章から利用者向けに)、上書き用 ini と WebUI の関係、アクセス制御、接続先(外部、複数、チューナー数、視聴に使う BonDriver、外したとき)、チャンネル定義(自動スキャン、再スキャン、ずれの警告、自分で用意した定義、`--force`)、HTTPS、pcscd の 2 通り、ハードウェアエンコード、同じホストに 2 つ置く場合、KonomiTV の接続例(動作は保証しないと明記)。btrfs の節は内容を保ち、見出しの位置だけ変えた。
- `docs/migration-v1-to-v2.md`: 変わる点、対応表、手順(控える、退避、更新、override と env、ビルド、v1 の `down`、所有者、起動、確認、片付け)、初回の起動で足されるもの、v1 のチャンネル定義の扱い、コンテナ名で操作していた場合、元に戻す方法。
- `compose.override-sample.yml`: 外部の接続先の案内を `EDCB_BACKEND_DEFAULT_URL` に、ハードウェアエンコードの見本の `BASE_IMAGE` を、ローカルでビルドした元のイメージ(`edcb-base:local`)に直した(配布イメージがまだ無いため)。
- `scripts/check-links.py` を足し、`scripts/check.sh` の `links` として実行する。git が無視しない `*.md` の相対リンクと、見出しへのアンカー(GitHub の規則)を確かめる。
- 結合テスト `tests/integration/phase6.sh`(T60、T61)。`lib.sh` に Compose のプロジェクトとボリュームの後片付けを、`run.sh` に既存のボリュームの確認を足した。
- `CLAUDE.md` から「進行中の作業」を外し、構成、設計資料、守ること、検証の方法に書き直した。

### 実装時に決めた点

- **必要な Docker Compose の版は 2.24.4**(`facts.md` の F9)。`!override` を最初に取り込んだ版。
- **リリースのタグは `v2.0.0` の形と仮定して書いた**(`release.yml` が semver のタグを受け付けるため)。違う名前にする場合は、Readme、Setup.md、移行手順の `v2.0.0` を直す。
- **配布イメージ(GHCR)の使い方は書いていない。** 公開が決まっていないため。手順は git のタグを指定してローカルでビルドする形にした。公開を決めたら、`compose.yml` の `image:` と、Readme の更新方法に配布イメージの節を足す。
- 移行で、v1 で `user:` を指定していなかった利用者は `edcb/ini` が root の所有になっている。v2 は 2 回目以降の起動で所有者を変えないので、`chown -R` を手順に入れた(`PUID=0` は勧めない)。
- 元に戻す手順のために、`git rev-parse HEAD` と v1 のイメージ(`docker tag`)を控える手順を入れた。v1 の最後のタグ `v1.0.4` には btrfs のパッチが入っていない(`main` の `8f38425` が v1 の最後)。
- ハードウェアエンコードの見本を、ローカルでビルドしたイメージの上に作る場合、`BASE_IMAGE` に `<プロジェクト名>-edcb` を指定すると、見本で作ったイメージ自身を元にしてしまう(同じ名前のため)。別の名前(`edcb-base:local`)で元のイメージをビルドする手順にした。

### 検証

- `scripts/check.sh`: pytest、shellcheck(`phase6.sh` を含む)、actionlint、compose、links、local-info がすべて PASS。
- リンクの検査が、存在しないファイルと見出しを見つけることを、壊したリンクで確かめた。
- 文書と実装の突き合わせ: 文書に出てくる環境変数を抜き出し、実装に無いものが廃止した `EDCB_CHECKOUT`(移行手順の対応表)だけであることを確かめた。`config.py` の既知の環境変数がすべて Setup.md の表にあること、`edcbctl` のサブコマンドが実装と同じであること、`edcbctl backends` / `status` の出力の例と、ずれの警告の文言がコードと同じであることを確かめた。
- `.env` の `EDCB_HOST_HTTP_PORT=<アドレス>:<ポート>` が `host_ip` 付きの公開になることを `docker compose config` で確かめた。
- T61 の v1 の構成の書き換えと、T60 のテスト用の重ね方(`COMPOSE_FILE`)が `docker compose config` を通ることを、デーモン無しで確かめた。
- **Docker が要る確認(T60、T61)は未実施。** ユーザに `sudo tests/integration/run.sh` を依頼する。

### 受け入れ条件の状況

| 条件 | 状況 |
|---|---|
| `Setup.md` の手順を空の一時ディレクトリで通す | 未確認(T60) |
| 環境変数、コマンド、ファイル名が実装と一致 | 確認(上の「検証」) |
| 移行手順を v1 を模した一時ディレクトリで通す | 未確認(T61) |
| リンクが切れていない | 確認(`scripts/check.sh` の links) |

### 公開の判断の材料(ユーザに渡す)

- ライセンス(`facts.md` の F8): EDCB のリポジトリには `LICENSE-Civetweb.md` しか無く、再配布条件の記載が見つからない。EMWUI はライセンスが検出されない(`LICENSE/` は同梱ライブラリのもの)。BonDriver_LinuxMirakc は MIT。配布イメージには EDCB と EMWUI のバイナリ・ファイルが入るので、GHCR で公開するかはユーザが決める。mirakc イメージ(libaribb25 入り)は配布しない(`decisions.md` の A4)。
- 公開する場合の手順: (1) `v2` を `main` にマージ、(2) `v2.0.0` などの semver のタグを push すると `release.yml` が amd64 / arm64 をビルドして `ghcr.io/<owner>/<repo>/edcb` に push する、(3) GitHub のパッケージの設定で public にする、(4) `compose.yml` に `image:` を足し、Readme に配布イメージでの更新方法を書く(このフェーズでは未実施)。
- 公開しない場合も、利用者はタグを指定してローカルでビルドできる(今の文書の形)。
- 定期チェック(`upstream-check.yml`)は、`main` に入るまで動かない。自動 PR で CI を動かすには `UPSTREAM_CHECK_TOKEN` が要る(`docs/v2/README.md` の「ユーザの作業が必要なもの」)。
