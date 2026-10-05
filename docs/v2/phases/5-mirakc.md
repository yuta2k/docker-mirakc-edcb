# フェーズ 5: mirakc コンテナとハードウェアエンコードの見本

## 目的

次の作業を行う。互いに独立しているので、コミットは分ける。作業 0 と 3 は、2026-10-05 にフェーズ 2 の実機確認を受けて追加した。作業 4 は、2026-10-06 にフェーズ 4 の申し送りを受けて追加した。

0. ベースイメージと依存の更新(作業 2 の見本が Ubuntu のパッケージ名に依存するので、先に行う)
1. mirakc コンテナで、内蔵の pcscd とホストの pcscd を切り替えられるようにする
2. Intel のハードウェアエンコードを足す拡張用の Dockerfile を、見本として置く
3. HLS 方式のリモート視聴の不具合を切り分けて直す(作業 2 の実機確認は HLS 方式で行うので、作業 2 の実機確認より前に行う)
4. 外した接続先の生成物を片付ける `edcbctl prune`

関連する方針: `decisions.md` の D3、F、G。仕様: `design.md` の 2、5、11 章。事実: `facts.md` の F7、F11。

## 先に確認すること

`facts.md` の U14 を確認する。

## 作業 0: ベースイメージと依存の更新

- **edcb のベースイメージ**: `ubuntu:24.04` から `ubuntu:26.04`(LTS)に上げる。
  - 先に、26.04 が公開されているか、EDCB のビルドに要るパッケージ(`liblua5.2-dev`、`lua-zlib`、`liblua5.2-0`、`ffmpeg`、`python3`、`procps`、`tzdata`)があるかを確かめる。無いものがあれば代わりを決める。
  - ほかのベース(Debian の安定版など)が明らかに適していれば、比べて提案してよい。決める前にユーザに確認する。比べる観点は、上記のパッケージの有無、ffmpeg の版と `--enable-libvpl`(作業 2)、サポート期間、arm64 対応。
  - EDCB と BonDriver のビルド、パッチの適用、スモークテスト、結合テスト(`tests/integration/run.sh`。空のディレクトリでの起動、権限、ヘルスチェック、HTTPS)が通ること。
  - Python の版はベースイメージに従う。pytest(`scripts/check.sh`。CI では `build.yml` の `check` ジョブ)が、イメージと同じ版の Python で動くようにする(`scripts/check.sh` の Python の版の指定を合わせる。ランナーに uv が無く、ランナーの Python の版が違うなら、`actions/setup-python` で版を合わせるか、ビルドしたイメージの中で pytest を動かす)。
- **mirakc のベースイメージを固定する**: 現在の `FROM mirakc/mirakc:debian` は動くタグで、再ビルドのたびに mirakc 本体と Debian sid のパッケージが変わる。フェーズ 2 の実機確認で、pcscd が polkit 有効の版に変わっていてスクランブル解除できなくなった(`facts.md` の U14)。
  - 版のタグ(例: `mirakc/mirakc:<版>-debian`。実際のタグの形は Docker Hub で確認する)とダイジェストで固定し、`ARG` の既定値を唯一の定義場所にする(`decisions.md` の A2 と同じ考え方)。
  - `upstream-check.yml` に、mirakc の新しい版を検出して固定を更新する PR を作る処理を足す(EDCB と同じ流れ)。
- **GitHub Actions**: ワークフローで使っているアクションの版(`actions/checkout`、`docker/*` など)を最新のメジャー版に上げる。actionlint を通す。
- **該当なし**: Node.js などは使っていない。プロビジョニングは Python の標準ライブラリだけなので、更新するライブラリは無い。
- 上流のバージョン(EDCB、BonDriver、EMWUI など)の固定の更新は、この作業の対象外(`upstream-check.yml` の定期チェックで行う)。

## 作業 1: mirakc コンテナ

- `mirakc/entrypoint.sh` を作り、Dockerfile の `ENTRYPOINT`(現在は `sh -c "pcscd && mirakc"`)を置き換える。
  - `/run/pcscd/pcscd.comm` がソケットとして存在する、または `DISABLE_PCSCD=1` のとき、内蔵の pcscd を起動しない。どちらを使っているかをログに出す
  - それ以外は従来どおり pcscd を起動してから mirakc を起動する
  - mirakc を `exec` で起動し、シグナルが届くようにする
- `compose.override-sample.yml` に、2 通りの書き方をコメント付きで載せる。
  - 内蔵: `devices` に USB を渡す。現在の `/dev/bus:/dev/bus` より狭く、`/dev/bus/usb` で足りるかを確認する
  - ホスト: `/run/pcscd/pcscd.comm` をマウントする。`devices` の USB は不要
- `compose.yml` の mirakc サービスを `design.md` の 2 章のとおりにする(既定で有効、override で無効にできる)。

## 作業 2: ハードウェアエンコードの見本

- `edcb/hwaccel/intel/Dockerfile` を作る。
  - `ARG BASE_IMAGE` を受け取り、`FROM ${BASE_IMAGE}` にする(既定は配布イメージ)
  - 既定では Ubuntu のリポジトリのパッケージだけを入れる。Intel の VA-API ドライバと VPL ランタイム、動作確認用の `vainfo`。必要なパッケージ名は、Ubuntu 24.04 のパッケージ情報で確認して決める(`-dev` パッケージは入れない)
  - `ARG QSVENCC_VERSION`(既定は空)。指定されたときだけ、rigaya/QSVEnc のリリースから `.deb` を取得して入れる。QSVEncC が要求する追加の依存や Intel の外部リポジトリが要るかは、QSVEnc の `Install.en.md` で確認する
  - amd64 専用であることを明記する
- `compose.override-sample.yml` に、見本を使う書き方をコメント付きで載せる(`build:` の指定、`devices` に `/dev/dri`)。`group_add` は不要(フェーズ 2 で、`/dev/dri/renderD*` の所有グループを自動で加える処理が入っている)。
- `edcb/Dockerfile` のコメントアウト部分(Intel Media Driver と QSVEncC)を削除する。
- CI: `upstream-check.yml`(週 1 回)に、見本のビルドを確認するジョブを足す。`QSVENCC_VERSION` は指定なしと、その時点の最新の両方で試す。公開はしない。
- 使い方の説明(どの `XCODE_OPTIONS.lua` の項目が使えるようになるか)は、フェーズ 6 の `Setup.md` に書くための材料として、実施記録に残す。

## 作業 3: HLS 方式のリモート視聴

フェーズ 2 の実機確認で、TS-Live! 方式は再生できたが、HLS 方式(`432p/h264/ffmpeg`)は再生できなかった(`phases/2-provision.md` の「実機確認の結果」)。

- 症状: `/api/mp4init` と `/api/segment` が 404。ffmpeg は約 17 秒変換したあと `Broken pipe` で終わる。入力に AAC と MPEG-2 のデコードエラーがあり、出力の音声がほとんど無い。
- 進め方(往復を減らすため):
  1. 実機で 1 回だけ、mirakc から 10〜30 秒の TS(`decode=1`)を取ってもらう(ユーザに依頼。地上波と BS を 1 つずつ)。
  2. 以降はチューナー無しで、その TS をイメージ内の `tsreadex | ffmpeg | tsmemseg -4` に、EMWUI の `api/view` と同じ引数で通して再現する。初期化データ(`tsmemseg_<キー>_00.fifo` の先頭)ができるか、ffmpeg のエラーが TS 自体に由来するか(`ffmpeg -i <TS> -f null -` でも出るか)を見る。
  3. `tsreadex` の引数(`-x 18/38/39 -a 9 -b 1 -c 5 -u 2` など)、`USE_MP4_HLS=0`(TS のままの HLS)、`XCODE_OPTIONS.lua` の版の違い(既存の利用者の `Setting/` には古い版が残る)で結果が変わるかを確かめる。
- v1 で HLS 方式が動いていたかは分かっていない。v2 での後退か、もともとの不具合かを実施記録に書く。
- 直せないとき(上流の不具合など)は、原因と回避策(TS-Live! を使う、など)を実施記録に書き、フェーズ 6 の `Setup.md` で案内する。

## 作業 4: 外した接続先の片付け(`edcbctl prune`)

フェーズ 4 の申し送りを受けて、2026-10-06 にユーザと合意して追加した。方針は「勝手に消さない。明示的なコマンドで片付ける」。

- 対象(「残骸」と呼ぶ):
  - 環境変数から外した接続先: 生成した ChSet4、`EpgTimerSrv.ini` の `[BonDriver_LinuxMirakc_<名前>[_T|_S].so]` セクション、`[TVTEST]` の該当する行、`.provision/` の `backend-<名前>.json`、`scan-<名前>.ChSet4.txt`、状態ファイルの `channels.<名前>` と ChSet4 の記録
  - 残っている接続先で、本数が 0 と分かっている種別: `EpgTimerSrv.ini` のセクションと `[TVTEST]` の行(ChSet4 は分割のときに消える。8.3)
- 起動時: 残骸を消さない。残っていれば、何が残っているかと `edcbctl prune` を警告で案内する。とくに、外した接続先の ChSet4 が残っていると、EDCB は `.so` の無い BonDriver を認識し、予約を割り当てて録画に失敗するおそれがある(`facts.md` の F3、F17)ことを伝える。
- `edcbctl prune [--diff]`:
  - 退避を取ってから片付ける。`--diff` は表示だけ。
  - 利用者が置いた・編集した ChSet4(状態ファイルに記録が無い、またはハッシュが違う)は消さずに警告する。
  - `[TVTEST]` は該当する行を除いて番号を詰め、`Num` を直す。一覧が空になっても `Num=0` を残す(キーが無いと、次の起動で既定の一覧が書かれる)。
  - ChSet5 は、複数の接続先でサービスを共有しうるので触らない(`chscan --all --rebuild` に任せる)。
  - 片付ける BonDriver に固定した予約(`tunerID >> 16` がそのセクションの `Priority`)は書き換えず、件数を表示する。EpgTimerSrv に問い合わせられないときは、その旨を表示する。
  - 何かを変えたら、再起動を案内し、`status` の内容を表示する(`chscan` と同じ)。
  - 終了コード: 成功(片付ける物が無い場合を含む)0、失敗 1、引数の誤り 2。
  - 接続先に届かず、保存した情報も無い接続先は、種別ごとの本数が分からないので、その接続先の種別の片付けはしない。

## 受け入れ条件

- [ ] (作業 0)edcb のイメージが新しいベースイメージでビルドでき、スモークテストと結合テスト(`tests/integration/run.sh`)が通る
- [ ] (作業 0)mirakc のベースイメージが版とダイジェストで固定され、`upstream-check.yml` が更新を検出できる
- [ ] (作業 0)CI の pytest が、イメージと同じ版の Python で通る。ワークフローが actionlint を通る
- [ ] (作業 3)HLS 方式(`432p/h264/ffmpeg`)のリモート視聴が再生できる。または、直せない理由と回避策が実施記録にある
- [ ] `docker build mirakc/` が成功する
- [ ] ソケットをマウントせずに起動すると、内蔵の pcscd が起動する(プロセス一覧で確認)
- [ ] ダミーのソケットを `/run/pcscd/pcscd.comm` にマウントして起動すると、内蔵の pcscd が起動しない
- [ ] `DISABLE_PCSCD=1` でも、内蔵の pcscd が起動しない
- [ ] `docker stop` で mirakc が速やかに終了する(10 秒の強制終了を待たない)
- [ ] `compose.override.yml` で mirakc を無効にした構成で、`docker compose config` が成功し、edcb だけが起動対象になる
- [ ] 見本の Dockerfile が、`QSVENCC_VERSION` の指定なしでビルドできる。できたイメージで `ffmpeg -hide_banner -encoders` に `h264_qsv` と `h264_vaapi` が出る
- [ ] `QSVENCC_VERSION` を指定してビルドでき、`qsvencc --version` が動く
- [ ] 見本のイメージでも、EpgTimerSrv が通常どおり起動する
- [ ] `edcb/Dockerfile` からコメントアウト部分が無くなっている
- [ ] (作業 4)接続先を外して起動すると、残骸は消えず、警告で `edcbctl prune` が案内される
- [ ] (作業 4)`edcbctl prune --diff` は何も変えずに片付ける内容を表示し、`edcbctl prune` は退避を取ってから片付ける。利用者の ChSet4 と ChSet5 は残る。片付けたあとの起動で警告が出ない
- [ ] (作業 4)種別の本数が 0 になったときのセクションと `[TVTEST]` の行も片付けられる

## 検証

チューナーとカードリーダーが無い環境でも、上の条件は確認できる(mirakc はチューナー設定が空でも起動する)。`mirakc/config.yml` は利用者のデータなので使わず、`config-sample.yml` をもとにした一時ファイルを使う。

## 実機確認の依頼

次の手順をまとめて、ユーザに依頼する。

- (作業 0)新しいベースイメージで、TS-Live! のリモート視聴と録画ができるか
- (作業 3)HLS 方式の切り分け用の TS の取得と、修正後の HLS 方式のリモート視聴
- 内蔵の pcscd で、従来どおりスクランブル解除ができるか
- ホストの pcscd のソケットをマウントした構成で、スクランブル解除ができるか(ホストとコンテナの pcsc-lite の版を記録する)
- Intel GPU のあるホストで、見本のイメージを使い、`ffmpeg-qsv` の項目でリモート視聴のトランスコードができるか(Intel GPU が無ければ「未確認」と記録する)

## 実施記録

### 進め方(2026-10-06)

- フェーズ 4 の申し送り(外した接続先の片付け)をユーザと相談し、「案どおりこのフェーズに含める」と決めた(作業 4)。
- エージェントは Docker デーモンを使えないので、Docker が要る確認は `tests/integration/phase5.sh`(T50〜T58)にまとめ、ユーザに `sudo tests/integration/run.sh` の実行を依頼する。作業 3 は、ユーザに TS の取得だけを依頼し、切り分けはチューナー無しで行う。

### 作業 0: ベースイメージと依存の更新

- edcb: `ubuntu:24.04` → `ubuntu:26.04`。26.04 は Docker Hub に公開済み(amd64 / arm64)で、必要なパッケージはすべて標準リポジトリにある(ffmpeg 8.0.1、Python 3.14、lua5.2 5.2.4、lua-zlib 1.4、`procps`、`tzdata`)。ほかのベースを比べる理由は無かった。
- pytest の Python: `scripts/check.sh` の `PYTHON_VERSION` を 3.14 にした。CI の `check` ジョブで `pipx install uv` を行い、uv に 3.14 を用意させる(ランナーの python3 は 3.12)。uv が無いときは python3 の版を比べ、違えば CI では FAIL、手元では警告にした。
- mirakc: `FROM mirakc/mirakc:${MIRAKC_VERSION}-debian@${MIRAKC_DIGEST}`(3.4.88、マルチプラットフォームのイメージのインデックスのダイジェスト)。ダイジェストと名前空間の接頭辞は両立しないので、`ARG ARCH` をやめた(別のアーキテクチャは `platform` でビルドできる)。
- `upstream-check.yml`: 既存のジョブを `edcb` に改名し、`mirakc` ジョブを足した。Docker Hub のタグ一覧から `<版>-debian` の最新を探し、レジストリの API でダイジェストを取得、`mirakc/Dockerfile` を書き換えてビルドと `mirakc --version` を行い、成功なら PR、失敗なら issue を作る(EDCB と同じ流れ)。検出の部分は手元で実行し、現在の版では `newer=false`、版を 1 つ戻すと `newer=true` になることを確かめた。
- GitHub Actions のアクションは、すでにすべて最新のメジャー版だった(`actions/checkout@v7`、`docker/setup-buildx-action@v4`、`docker/build-push-action@v7`、`docker/login-action@v4`、`docker/metadata-action@v6`、`actions/upload-artifact@v7`、`actions/download-artifact@v8`。2026-10-06 に各リポジトリの最新リリースで確認)。

### 作業 1: mirakc コンテナ

- `mirakc/entrypoint.sh`: `DISABLE_PCSCD=1` なら起動しない。`/run/pcscd/pcscd.comm` か `/run/pcscd` がマウントされていて(`/proc/self/mountinfo`)、ソケットがあれば、ホストの pcscd を使う。マウントされているのにソケットが無いときは、内蔵の pcscd も起動せずに警告する(ホストのディレクトリに内蔵の pcscd のソケットを作らないため)。それ以外は、残っているソケットと PID のファイルを消してから `pcscd --disable-polkit` を起動する。どの場合もログに出し、pcsc-lite の版も出す(ホストとの版の違いを調べるため)。最後に `exec mirakc`。
- **設計から足した点**: 単純な `-S` の判定では、`docker restart` のあとに内蔵の pcscd が残したソケットを「ホストのもの」と誤判定する。マウントの有無で判定するようにした(T55 で確認する)。
- `compose.yml` の mirakc から `devices: /dev/bus:/dev/bus` を外した(ホスト固有の値、design.md 2 章)。`compose.override-sample.yml` に、内蔵の pcscd 用の `/dev/bus/usb`、ホストの pcscd 用のソケットのマウント(`create_host_path: false` の長い書式。ホストにソケットが無いときに Docker がディレクトリを作らないように)、`DISABLE_PCSCD=1` を載せた。`/dev/bus/usb` で足りるかは実機確認で確かめる。

### 作業 2: ハードウェアエンコードの見本

- `edcb/hwaccel/intel/Dockerfile`: `ARG BASE_IMAGE`(既定は `ghcr.io/yuta2k/docker-mirakc-edcb/edcb:latest`。release.yml のイメージ名)。Ubuntu の標準リポジトリから `intel-media-va-driver-non-free`、`libmfx-gen1.2`、`vainfo` を入れる。`QSVENCC_VERSION` を指定したときだけ `qsvencc_<版>_amd64.deb` を取得して apt で入れる(`QSVENCC_SHA256` を指定すれば検査する)。amd64 以外ではビルドを失敗させる。
- 26.04 の ffmpeg は最初から VPL と VA-API が有効なので、`h264_qsv` と `h264_vaapi` は配布イメージの ffmpeg にも出る。見本が足すのはドライバとランタイム。
- `edcb/Dockerfile` のコメントアウト部分を削除した。
- `upstream-check.yml` に `hwaccel-intel` ジョブを足した。edcb をビルドし、それを `BASE_IMAGE` にして、QSVEncC 無しと最新版の 2 通りで見本をビルドし、`.github/scripts/hwaccel-intel-test.sh` で確かめる(公開しない)。
- **Setup.md の材料**(フェーズ 6): 見本と `/dev/dri` で使えるようになる `XCODE_OPTIONS.lua` の項目は、`720p/h264/ffmpeg-qsv`(QSV。Gen12 = Tiger Lake 以降)。`QSVENCC_VERSION` を指定すると `720p/h264/QSVEncC` と `720p/hevc/QSVEncC` も使える(Gen11 以前は `--backend vaapi` が要る。既定の項目にはその指定が無い)。`h264_vaapi` を使う項目は既定には無い(利用者が `Setting/XCODE_OPTIONS.lua` に足す)。

### 作業 4: `edcbctl prune`

- `edcb_provision/prune.py`。対象の BonDriver は、`EpgTimerSrv.ini` のセクション、`[TVTEST]` の行、`Setting/` の ChSet4 のファイル名、状態ファイルの記録、`.provision/` のファイルから集める。名前の解釈は `BonDriver_LinuxMirakc[_<名前>][_T|_S].so`(大文字小文字を区別しない)。
- 予約のチューナー固定を数えるため、`ctrlcmd.py` の予約の読み取りを `REC_SETTING_DATA` の `tunerID` まで広げた(`Common/CtrlCmdUtil.cpp`)。EDCB のチューナー ID は `Priority << 16 | 連番`(`ReserveManager.cpp` の `Initialize`)。
- **設計から変えた点**: 本数が 0 になった種別の、利用者が置いた・編集した ChSet4 については、起動時も prune でも警告しない。その BonDriver は `Count=0` か、セクションが無いので EDCB は使わず、害が無いため(既存のテスト `test_edited_generated_file_is_left_alone` の前提とも合う)。外した接続先の利用者の ChSet4 は、`.so` が無いので警告する。
- ini の編集に、セクションを丸ごと消す `IniFile.delete_section` を足した。

### 検証(エージェントが実行したもの)

- `scripts/check.sh`: pytest(Python 3.14、178 件成功、1 件 SKIP)、shellcheck、actionlint、compose、local-info がすべて PASS。
- `docker compose config`(デーモン不要): mirakc を無効にした override で、`--services` が `edcb` だけになることを確かめた。ソケットのマウントの長い書式も通った。

### 結合テスト(2026-10-06、ユーザが実行)

`sudo tests/integration/run.sh`(コミット `bb52630`): **43 件すべて PASS**(T0〜T49 の回帰を含む)。edcb は Ubuntu 26.04 でビルドでき、パッチ、プロビジョニング、権限、ヘルスチェック、HTTPS、スキャンの確認が通った。

| 確認 | 結果 |
|---|---|
| T50 `docker build mirakc/` | PASS |
| T51 ソケット無しで内蔵の pcscd が起動 | PASS(ログに pcsc-lite の版) |
| T52 ダミーのソケットをマウントすると起動しない | PASS |
| T53 `DISABLE_PCSCD=1` で起動しない | PASS |
| T54 `docker stop` が 10 秒を待たずに終わる(`--init` の有無の両方) | PASS |
| T55 `docker restart` のあとも内蔵の pcscd が起動する | PASS |
| T56 mirakc を無効にした override で、`docker compose config` が edcb だけ | PASS |
| T57 見本が QSVEncC 無しと 8.32 でビルドでき、`h264_qsv`、`h264_vaapi`、`vainfo`、`qsvencc --version`、EpgTimerSrv が healthy | PASS |
| T58 接続先を外したときの起動時の警告と `edcbctl prune` | PASS |

### 作業 3: HLS 方式の切り分け(途中)

- ユーザに、実機のバックエンドから地上波と BS の TS を 1 チャンネルずつ、30 秒ずつ取ってもらった(`decode=1`)。
- TS 自体のデコードエラーは先頭の数件だけ(途中から受信を始めたため)。TS に由来する問題ではない。
- EDCB の `Makefile` と同じ版の tsreadex(`master-260428`)と tsmemseg(`master-with-d-260611`)をホストでビルドし、EMWUI の `api/view` と同じ引数のパイプラインに、TS をライブと同じ速さで流して再現した(ホストの ffmpeg は 9.0.1)。
  - fMP4 の初期化データ(moov)とセグメントはできた。ただし、**最初のセグメントまで約 16 秒**かかった。
  - 原因: 字幕を出力に含める指定(`captionHls` の `-map 0:s? -scodec copy`)があると、ffmpeg は字幕のパケットが届くまで出力を始めない(字幕を外すと 1.7 秒で出力が始まる)。tsreadex の `-c 5` は、字幕が無いときに非表示の字幕データを差し込むが、差し込むのは **15 秒**字幕が無かったとき(`servicefilter.cpp` の `INSERT_MANAGEMENT_DETERMINE_ABSENCE_SEC`。2023-08 から。Readme の「5 秒ごと」は古い)。字幕の無い番組では、HLS の開始が約 16 秒遅れる。
  - EMWUI のクライアント(`E3/js/ts-loader.js` の `#waitForHlsStart`)は、プレイリストにセグメントが現れるまで 200 ms ごとに問い合わせ続け、打ち切らない。遅れるだけで、それだけでは再生できない理由にならない。
  - ホストの ffmpeg 9.0.1 では、出力の音声も正常だった(GR、BS とも約 30 秒で 590 kB)。実機の症状(音声がほぼ空、約 17 秒で Broken pipe、`mp4init` が 404)は再現しない。イメージ内の ffmpeg 8.0.1 で同じ確認をする(ユーザに依頼)。
