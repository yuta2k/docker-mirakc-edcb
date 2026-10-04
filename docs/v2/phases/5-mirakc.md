# フェーズ 5: mirakc コンテナとハードウェアエンコードの見本

## 目的

次の作業を行う。互いに独立しているので、コミットは分ける。作業 0 と 3 は、2026-10-05 にフェーズ 2 の実機確認を受けて追加した。

0. ベースイメージと依存の更新(作業 2 の見本が Ubuntu のパッケージ名に依存するので、先に行う)
1. mirakc コンテナで、内蔵の pcscd とホストの pcscd を切り替えられるようにする
2. Intel のハードウェアエンコードを足す拡張用の Dockerfile を、見本として置く
3. HLS 方式のリモート視聴の不具合を切り分けて直す(作業 2 の実機確認は HLS 方式で行うので、作業 2 の実機確認より前に行う)

関連する方針: `decisions.md` の D3、F、G。仕様: `design.md` の 2、5、11 章。事実: `facts.md` の F7、F11。

## 先に確認すること

`facts.md` の U14 を確認する。

## 作業 0: ベースイメージと依存の更新

- **edcb のベースイメージ**: `ubuntu:24.04` から `ubuntu:26.04`(LTS)に上げる。
  - 先に、26.04 が公開されているか、EDCB のビルドに要るパッケージ(`liblua5.2-dev`、`lua-zlib`、`liblua5.2-0`、`ffmpeg`、`python3`、`procps`、`tzdata`)があるかを確かめる。無いものがあれば代わりを決める。
  - ほかのベース(Debian の安定版など)が明らかに適していれば、比べて提案してよい。決める前にユーザに確認する。比べる観点は、上記のパッケージの有無、ffmpeg の版と `--enable-libvpl`(作業 2)、サポート期間、arm64 対応。
  - EDCB と BonDriver のビルド、パッチの適用、スモークテスト、フェーズ 2 の検証スクリプト一式(空のディレクトリでの起動、権限、ヘルスチェック、HTTPS)が通ること。
  - Python の版はベースイメージに従う。CI の pytest(`build.yml` の `test` ジョブ)が、イメージと同じ版の Python で動くようにする(ランナーの Python が違うなら `actions/setup-python` で版を合わせるか、ビルドしたイメージの中で pytest を動かす)。
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

## 受け入れ条件

- [ ] (作業 0)edcb のイメージが新しいベースイメージでビルドでき、スモークテストとフェーズ 2 の検証スクリプトが通る
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

(着手したエージェントが書く)
