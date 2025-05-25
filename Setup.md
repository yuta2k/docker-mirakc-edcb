
# セットアップ方法

原則、各種ソフトウェアの最新コミットを使用してビルドするため、実情と異なる可能性があります。

## 事前準備

* Docker を導入
* ホストの pcscd を停止
* `mirakc/config-sample.yml` を参考に `mirakc/config.yml` を作成・記入する  
  あるいは [ISDBScanner](https://github.com/tsukumijima/ISDBScanner) などで生成する  
  mirakc のドキュメント: https://mirakc.github.io/dekiru-mirakc/stable/config/
* `compose-sample.yml` を参考に `compose.yml` を作成・記入する  
  * mirakc: `devices` にチューナのデバイスファイルの場所を記述
  * edcb: `volumes` に録画ファイルの保存先を指定
  * ほかお好みで改変してください
* 必要であれば、次の場所に edcb コンテナを実行するユーザが読み書きできるよう、所有者・パーミッションを設定
  * `edcb/ini`
  * `volumes` で指定した録画ファイルの保存先

## ビルド・起動

ビルド・起動し、EDCB の設定ファイルを生成します。

```
# docker compose up -d
```

## チャンネル設定

チャンネルスキャンを実行するか、チャンネル定義ファイルを配置します。

### チャンネルスキャン

次のコマンドを実行します。

```
# docker compose exec edcb EpgDataCap_Bon -d BonDriver_LinuxMirakc.so -chscan
```

完了後、 `edcb/ini/Setting/` 下に以下のファイルが生成されます。

* `BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt`
* `ChSet5.txt`


地上波または BS・CS 専用チューナを含む場合、 [EDCB-Wine の説明](https://github.com/tsukumijima/EDCB-Wine?tab=readme-ov-file#4-edcb-%E3%81%AE%E8%A8%AD%E5%AE%9A)を参考に次のファイルも作成すると良いでしょう。

* `BonDriver_LinuxMirakc_S(LinuxMirakc).ChSet4.txt`
* `BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt`

作業完了後

```
# docker compose restart edcb
```

で EDCB (EpgTimerSrv) を再起動し、反映します。

### ISDBScanner の出力結果を使用する

[ISDBScanner](https://github.com/tsukumijima/ISDBScanner) をお使いの場合 `EDCB-Wine` 用の設定を流用し、 `edcb/ini/Setting/` 下に次のファイルを配置することができます。  
ChSet4.txt のファイル名が異なりますので、注意してください。

* `BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt`
* `BonDriver_LinuxMirakc_S(LinuxMirakc).ChSet4.txt`
* `BonDriver_LinuxMirakc_T(LinuxMirakc).ChSet4.txt`
* `ChSet5.txt`

配置後

```
# docker compose restart edcb
```

で EDCB (EpgTimerSrv) を再起動し、反映します。


## EDCB のアクセス制御設定

`edcb/ini/EpgTimerSrv.ini` の `HttpAccessControlList` に WebUI などへアクセスを許可する接続元を追記します。  
例: LAN のサブネット `,+192.168.x.0/24` など

この `Setup.md` を書いた時点で `EnableHttpSrv=2` がデフォルトでアクセスログが生成されますが、肥大化していく傾向がありました。  
`1` に変更・無効化し、必要であれば別の手段でアクセスログを摂るべきかもしれません。

詳細はこちら: [tkntrec 版 EDCB a494558 コミット](https://github.com/tkntrec/EDCB/blob/a49455807fe98c9396b443d9e56d017fede3562f/Document/Readme_Mod.txt#civetweb%E3%81%AE%E7%B5%84%E3%81%BF%E8%BE%BC%E3%81%BF%E3%81%AB%E3%81%A4%E3%81%84%E3%81%A6)

変更後

```
# docker compose restart edcb
```

で EDCB (EpgTimerSrv) を再起動し、反映します。

## EDCB のほか設定

現状 Linux 版 EDCB は、主にブラウザから Legacy WebUI を操作して設定・管理を行います。  

初期状態では Legacy WebUI からの設定変更が禁止されているため、次のようにシェルスクリプトを実行し、許可するよう変更します。

```
# sh chlegacyset.sh true
```

Legacy WebUI には `http://ホストの IP アドレスなど:5510/legacy` でアクセスします。  
「設定メニュー」より最低限、次のような設定を行うとよいでしょう。

* 基本設定 - 録画保存フォルダ  
  `compose.yml` の `volumes` に追加した場所を指定
* 基本設定 - BonDriver  
  チューナー数を指定  
  BonDriver は [EDCB-Wine](https://github.com/tsukumijima/EDCB-Wine?tab=readme-ov-file#1-%E5%8B%95%E4%BD%9C%E7%A2%BA%E8%AA%8D%E7%92%B0%E5%A2%83) を参考に次のような構成としています
  * `BonDriver_LinuxMirakc.so` : 地上波・BS・CS チューナ用
  * `BonDriver_LinuxMirakc_T.so` : 地上波専用チューナ用
  * `BonDriver_LinuxMirakc_S.so` : BS・CS 専用チューナ用
* 録画アプリ(EpgDataCap_Bon)  
  EMWUI 向けに「ロゴデータを保存する」をチェック
* EMWUI でリモート視聴を使いたい場合:
  * 録画アプリ(EpgDataCap_Bon) - ネットワーク設定 - TCP送信先  
    SrvPipe, 0.0.0.1:0 を追加
  * 設定/視聴に使用するBonDriver  
    BonDriver を追加

## EPG 取得

Legacy WebUI などで [EPG取得] ボタンを押します。  
しばらくすれば「番組表」が埋まっていくと思いますが、失敗する場合は次のコマンドで実行し、ログを得ることができます。

```
# docker compose exec edcb EpgDataCap_Bon -d BonDriver_LinuxMirakc.so -epgcap
```

## 動作確認後

落ち着いたところで Legacy WebUI からの設定を再び禁止すると、セキュリティ的に安心できると思います。

```
# sh chlegacyset.sh false
```

その後再び設定を変更したい場合、

```
# sh chlegacyset.sh true
```

を実行してください。

## (動作検証方法)

Windows 版で GUI が用意されている `EpgDataCap_Bon` はコマンドラインからの起動となります。  
`-h` の引数をつけるとヘルプが表示されます。

```
# docker compose exec edcb EpgDataCap_Bon -h
```

例えばチャンネル定義・スキャン後に次のコマンドで立ち上げると、Ctrl+C を押すまで BS11 の Signal・Drop・Scramble カウントなどを表示できます。  
BonDriver_LinuxMirakc による mirakc への接続エラーログも表示できます。

```
# docker compose exec edcb EpgDataCap_Bon -d BonDriver_LinuxMirakc.so -nid 4 -tsid 16528 -sid 211
```
