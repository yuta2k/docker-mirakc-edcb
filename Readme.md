# docker-mirakc-edcb

* [mirakc](https://github.com/mirakc/mirakc)
* [tkntrec 版 EDCB](https://github.com/tkntrec/EDCB)
* [EDCB_Material_WebUI](https://github.com/EMWUI/EDCB_Material_WebUI)
* [BonDriver_LinuxMirakc](https://github.com/matching/BonDriver_LinuxMirakc)

等を組み合わせた Docker Compose 用ファイル群

EDCB の設定ファイルには介入しないため、セットアップに手動での操作がやや必要です。

## 前提条件

* Docker を導入
* ホストの pcscd を停止する
* `mirakc/config.yml` 用のチャンネル定義を用意する手段がある  
  一応、自前でチャンネルスキャンを持つ Mirakurun に書き換えても動作すると思われます

## セットアップ

[Setup.md](Setup.md) を参照してください。

## EDCB へのアクセス

主にブラウザから操作します。

* Legacy WebUI: 主に EDCB・EpgTimerSrv の設定、管理などを行います  
  `http://ホストの IP アドレスなど:5510/legacy`
* EDCB_Material_WebUI (EMWUI) : 録画予約・管理・ストリーミング視聴などを行います  
  `http://ホストの IP アドレスなど:5510/EMWUI`
* EpgTimerNW: Windows クライアントより高度な EPG などを利用できます  
  EpgTimerNW は tkntrec 版か、互換性のあるフォークを使用してください。  
  ただし、次の設定は Legacy WebUI から行います。
  * EpgTimerNW による接続の許可 (設定メニュー - その他)
  * 録画のプリセット (設定メニュー - プリセット)

## ほか

### 更新方法

```
# docker compose build --no-cache
# docker compose up -d
```

### 外部の mirakc・Mirakurun を使用する場合

`compose.yml` を改変し EDCB のみを実行する場合など。  
edcb コンテナの環境変数 `MIRKAC_ADDRESS` で mirakc または Mirakurun のアドレスを指定できます。

IP アドレスで指定する場合は、特に問題ありません。

ホスト名が指定された場合には、コンテナ立ち上げ時にのみ名前解決を行います。  
`external_network` を利用したり、IP アドレスが変わる可能性のあるホストへ接続する場合、注意してください。

## 課題

* 上記 `BonDriver_LinuxMirakc` のホスト名の名前解決
* SrvPipe 使用時に `edcb/ini` (コンテナ内 `/usr/local/edcb/` ) 下に作成される *.fifo ファイルを随時削除したい  
  一旦、コンテナ起動時に掃除するようにしている
