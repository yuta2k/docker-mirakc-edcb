# フェーズ 5: mirakc コンテナとハードウェアエンコードの見本

## 目的

2 つの小さな作業を行う。互いに独立しているので、コミットは分ける。

1. mirakc コンテナで、内蔵の pcscd とホストの pcscd を切り替えられるようにする
2. Intel のハードウェアエンコードを足す拡張用の Dockerfile を、見本として置く

関連する方針: `decisions.md` の D3、F、G。仕様: `design.md` の 2、5、11 章。事実: `facts.md` の F7、F11。

## 先に確認すること

`facts.md` の U14 を確認する。

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

## 受け入れ条件

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

- 内蔵の pcscd で、従来どおりスクランブル解除ができるか
- ホストの pcscd のソケットをマウントした構成で、スクランブル解除ができるか(ホストとコンテナの pcsc-lite の版を記録する)
- Intel GPU のあるホストで、見本のイメージを使い、`ffmpeg-qsv` の項目でリモート視聴のトランスコードができるか(Intel GPU が無ければ「未確認」と記録する)

## 実施記録

(着手したエージェントが書く)
