# 確認済みの事実と未確認の点

2026-10-04 時点で、上流のソースを読んで確認した内容です。上流は変わるので、実装前に該当箇所を自分でも確認してください。誤りを見つけたら、このファイルを直してください。

## 固定に使う値(2026-10-04 時点)

| 対象 | リポジトリ | タグ / コミット |
|---|---|---|
| EDCB | `xtne6f/EDCB` | タグ `work-plus-s-260904` = `ebf50c730ccf8c1732e0bd8a4e2a3417a94d9b2b` |
| BonDriver | `matching/BonDriver_LinuxMirakc` | `cfbefc6d21dab4009db5f124984c1b720b76d869`(2024-10-14、以降更新なし) |
| EMWUI | `EMWUI/EDCB_Material_WebUI` | `4e5b5c865a481cc8f443d6d468ee9571a8bfcf20`(2026-10-02 時点の HEAD。既定ブランチ `E3`) |
| lua | `xtne6f/lua` | `00e941f334ea08557a8c0c428203456387d54eb3`(ブランチ `v5.2-luabinaries` の 2026-10-04 時点の HEAD) |
| lua-zlib | `xtne6f/lua-zlib` | `dc3ea17156ad727398ab39501d3cd03e32324165`(ブランチ `v0.5-lua52` の 2026-10-04 時点の HEAD) |
| libaribb25 | `tsukumijima/libaribb25` | `dc1d96a90ea554d8997b238fd6712eccf553cdb3`(2026-10-04 時点の HEAD。mirakc イメージ用) |

EMWUI の上記コミットと EDCB `260904` の組み合わせで、`/legacy/` と `/E3/` が HTTP 200 を返すことを確認した(フェーズ 1、U2)。

## 確認済み

### F1. tkntrec 版と xtne6f 版の差

- `EpgTimer/`(Windows クライアント)以外の差分は 6 ファイル、約 20 行。
- Linux の動作に影響するのは 1 点だけ。tkntrec 版は `EpgTimerSrvMain.cpp` で `compatFlags = 4095` に決め打ち、xtne6f 版は `EpgTimerSrv.ini` の `[SET] CompatFlags`(既定 0)を読む。
- 残りはバージョン文字列と、Windows 専用の設定ダイアログ(`SettingDlg.cpp` は Makefile で Windows のときだけビルド対象)。
- Legacy WebUI では `CompatFlags` は閲覧のみ(`setting_other.html`)。ini に書く必要がある。
- 現在の btrfs パッチ 2 本は `work-plus-s-260904` に `git apply --check` で当たる。
- EDCB のソースは改行が CRLF。`git am` は既定で行末の CR を取り除くため、`--keep-cr` を付けないとパッチが当たらない(フェーズ 1 で確認。付けると `warning: quoted CRLF detected` が出るが、適用には影響しない)。
- `EpgTimerSrv -h` と `EpgDataCap_Bon -h` は `Ver. work+s-260904` を表示し、終了コード 2 で終わる(`-h` の処理が `return 2`)。

### F2. 上流の歴史改変

- tkntrec 版はブランチをリベースする。`Setup.md` がリンクしている `a494558` は、どのブランチからも到達できない。
- xtne6f 版も改変する(`work-plus-s-260825` は現在のブランチの祖先ではない)。ただしタグがあるので、タグが指すコミットは消えない。
- xtne6f 版のリリース間隔は直近で 2〜8 週間。

### F3. EDCB の Linux 版の作り

- 設定の置き場所は `/var/local/edcb`、ライブラリは `/usr/local/lib/edcb`。どちらもコンパイル時のマクロ(`Common/PathUtil.h` の `EDCB_INI_ROOT` / `EDCB_LIB_ROOT`)。
- `make setup_ini`(`Document/Unix/Makefile`)は、ファイルが無いときだけ `Bitrate.ini`、`BonCtrl.ini`、`ContentTypeText.txt`、`HttpPublic/`、`EpgTimerSrv.ini` を作る。`EpgTimerSrv.ini` の初期値は `EnableHttpSrv=2` と localhost のみの ACL。
- **EDCB が認識する BonDriver の一覧は、`Setting/` にある `*.ChSet4.txt` のファイル名から作られる**(`EpgTimerSrvSetting.cpp` の `EnumBonFileName`)。`(` より前の部分に `.so` を付けたものが BonDriver 名になる。ChSet4 が無い BonDriver は存在しない扱い。
- ChSet4 のファイル名は `<BonDriver のファイル名から拡張子を除いたもの>(<チューナー名>).ChSet4.txt`。BonDriver_LinuxMirakc のチューナー名は `LinuxMirakc` 固定。
- チューナー数は `EpgTimerSrv.ini` の `[<BonDriver ファイル名>]` セクションの `Count`、`GetEpg`、`EPGCount`、`Priority`。Legacy WebUI(`setting_bon.html`)からも書かれる。
- スキャン結果の保存(`BonCtrl/ChSetUtil.cpp` の `SaveChSet`)は、ChSet4 を上書きし、**ChSet5 は既存の内容に追加する(マージ)**。古いサービスは ChSet5 から消えない。
- `-chscan` は `EpgDataCap_Bon -d <BonDriver>.so -chscan` で実行する(`EpgDataCap_BonMin.cpp`)。
- ChSet4 の列: 名前、サービス名、ネットワーク名、space、ch、ONID、TSID、SID、サービス種別、ワンセグ、表示フラグ、リモコン ID。タブ区切り、UTF-8(BOM 付き)。
- `EpgTimerSrv` の `ReloadSetting` は `ChSet5.txt` を読み直す(`ReserveManager.cpp`)。コマンドラインから呼ぶ手段は未確認。
- デバッグログは `/var/local/edcb/EpgTimerSrvDebugLog.txt` と `EpgDataCap_Bon_DebugLog-N.txt` に出る。標準出力には出ない。
- `HttpPublicFolder` という設定キーがあり、ソースで読まれている。Legacy WebUI からは変更できない。
- Legacy WebUI から変更できないキー: `HttpAccessControlList`、`EnableHttpSrv`、`HttpPort`、`HttpPublicFolder`、`HttpNumThreads`、`BonCtrl.ini` の `EpgCapTimeOut` / `ChChgTimeOut`。
- HTTPS: `HttpPort` に `s` 付きのポート(例 `5511s`)があると、EDCB のルートフォルダの `ssl_cert.pem` を使う(`Document/Readme_Mod.txt`)。Linux では `libssl.so.3` / `libcrypto.so.3` を実行時に読み込む(`civetweb.c`)。
- 録画開始時の容量確保は `Write_Default/WriteMain.cpp` の `fallocate`。`KeepDisk=0` にすると予定サイズが 0 になり、確保も、予定サイズによるフォルダ選択も行われない(`TunerBankCtrl.cpp`)。
- `tsidmove-edcb` が `make install` でインストールされる(BS 再編時の予約移行ツール)。

### F4. BonDriver_LinuxMirakc の作り

- ini は `<.so 自身のパス>.ini` から読む(`dladdr` の結果に `.ini` を付ける)。別名で置けば、接続先ごとに ini を分けられる。現在のイメージは 3 つの ini を同じファイルへのシンボリックリンクにしているので、別名ごとに別 ini が読まれることは未実証。**コピーで置くこと。**
- ini のキー: `SERVER_HOST`、`SERVER_PORT`、`SERVER_SOCKPATH`、`SERVER_TYPE`(`http` / `unix`)、`DECODE_B25`、`PRIORITY`、`SERVICE_SPLIT`。
- **ホスト名が使えない理由**: `http_proc.hpp` の `MirakcConnectHttp` が `inet_addr()` しか呼んでいない。`getaddrinfo` を使うコードは `#if 0` で残っている。
- **チューニング空間の決まり方**: 起動時に `/api/channels` を取得し、**同じ `type` が連続する区間**ごとに space を 1 つ割り当てる(`InitChannel`)。space 内の ch は、その区間内の 0 始まりの位置。つまり ChSet4 の space / ch は、mirakc 側のチャンネルの並び順に対する位置インデックス。mirakc の `config.yml` でチャンネルを途中に足すと、番号がずれる。
- `SERVICE_SPLIT=1` のときは `/api/services` を使う。既定は 0。
- **固定長バッファ**: API 応答の本体を `malloc(128 * 1024)` に、応答ヘッダを `char respHeader[512]` に、長さを確認せずコピーしている(`SendRequest`、`sendGetRequest_WaitBody`)。
- **再接続なし**: 受信スレッド(`RecvThread`)は切断を検知すると `disconnect()` して終了する。再接続の処理は見当たらない。
- 優先度は `X-Mirakurun-Priority` ヘッダで送る。

### F5. mirakc / Mirakurun の API

- mirakc の `/api/services` には TSID が含まれない(`mirakc-core/src/models.rs` の `MirakurunService`)。API だけでチャンネル定義は作れない。
- `/api/tuners` は各チューナーの `types`(`GR` / `BS` / `CS` / `SKY` の配列)を返す。
- mirakc は空いているチューナーを設定の並び順で割り当てる。両対応チューナーが地上波に先に使われると、衛星が取れなくなる。

### F6. EMWUI

- **2026-04-19 に「E3」(EMWUI 3)がベータ公開され(コミット `1c95d4c`)、2026-07-17 に旧 `HttpPublic/EMWUI/` が削除された(コミット `a7aeb2d`)。** 現在の既定ブランチは `E3`。WebUI のパスは `/E3/`。旧版はブランチ `EMWUI` に残っている。
- これまでのイメージはビルド時点の HEAD を使っていたので、既定ブランチが `E3` になってからビルドした利用者は、すでに E3 を使っている。ボリュームには `cp -ru` で旧 `EMWUI/` と `E3/` が並んで残る(この開発環境の `edcb/ini/HttpPublic` で確認)。既定ブランチが切り替わった日付は未確認。
- 設定変更の許可の処理は、E3 でも `HttpPublic/api/util.lua` にある(固定したコミットで確認)。
- README に「PWA や TS-Live! に SSL/TLS による通信が必須なため、HTTPS での運用を前提」とある。
- 視聴ページは `Cross-Origin-Embedder-Policy: require-corp` と `Cross-Origin-Opener-Policy: same-origin` を返し、TS-Live! は `SharedArrayBuffer` と WebGPU を使う。HTTP + LAN の IP アドレスでは動かない。
- README の推奨設定: `HttpPort=5510,5520,5511s,5521s`、`HttpNumThreads=50`(SSE が表示ごとにスレッドを 1 つ占有するため)。
- 設定ページからの変更は、既定では localhost からのアクセスだけ許可。`Setting/HttpPublic.ini` の `[SET] ALLOW_SETTING_LIST`(既定 `127.0.0.1,::1`)で許可元を足す(`api/util.lua`)。
- EMWUI は `Setting/` に `HttpPublic.ini` と `XCODE_OPTIONS.lua` を置く。現在の entrypoint は `cp -rn` なので、初回しかコピーされない。

### F10. WebUI の設定の書き込み方と、設定変更の許可

- Legacy WebUI は、オフにした項目を `0` の書き込みで表す。キーは削除しない(`setting_app.html` の `SaveLogo` / `SaveDebugLog`、`setting_app_network.html` の `[SET_TCP] Count`。WebUI で設定した実際の ini でも `Data=0` のように残ることを確認)。
- キーを削除するのは、空にしたパス(`DataSavePath`、`RecExePath`、`RecInfoFolder`)と、件数が減ったリストの余り(`IP<N>` / `Port<N>`、`DEL_EXT`、`EPG_CAP` など)。いずれもプロビジョニングが既定値を書かないキー。
- Legacy WebUI の設定変更の可否は、`legacy/util.lua` のグローバル変数 `ALLOW_SETTING`。各設定ページが POST のたびに参照する。同ファイルのコメントに「リモートアドレスと比較して接続元の限定も可能」とあり、式を書ける。現在の `chlegacyset.sh` は起動中に `sed` で書き換えており、再起動なしで効いている。
- EMWUI は `api/util.lua` で、`Setting/HttpPublic.ini [SET]` の `ALLOW_SETTING`(既定 true)と `ALLOW_SETTING_LIST`(既定 `127.0.0.1,::1`)をリクエストのたびに読む。

### F11. ハードウェアエンコード

- EDCB の `XCODE_OPTIONS.lua` の既定の項目が使うのは、ffmpeg(`libx264`、`h264_nvenc`、`h264_qsv`、`h264_amf`)、NVEncC、QSVEncC、VCEEncC。
- Ubuntu 24.04 の ffmpeg(6.1.1-3ubuntu5)は `--enable-libvpl` でビルドされている(Intel の cartwheel-ffmpeg の Issue 322 の記載による。コンテナ内では未確認)。
- 現在の Dockerfile のコメントアウト部分は QSVEncC 7.82 を固定しているが、2026-10-03 時点の最新は 8.32 で、配布ファイル名の形も変わっている(`qsvencc_8.32_amd64.deb`)。そのままでは動かない。
- QSVEncC の導入手順(`Install.en.md`)によると、QSV には VPL ランタイム(Tiger Lake 以降は `libmfx-gen`、それ以前は `libmfx1`)が要る。VA-API だけで動かすモードもある。

### F7. pcsc-lite

- 内部プロトコルの版: 2.0 系まで 4:4、2.3〜2.4.0 が 4:5、2.5 系が 4:6(`src/winscard_msg.h`)。
- 2.4.1 から、サーバもクライアントも 4:4 までの後方互換を持つ。それより前は、版が一致しないと通信を打ち切る。
- Mirakurun 公式のコンテナは、環境変数 `DISABLE_PCSCD=1` で内蔵の pcscd を止められる。
- mirakc の Dockerfile は既定で Debian sid ベース(`ARG DEBIAN_CODENAME=sid`)。配布イメージの実際の版は未確認。

### F8. ライセンス

- EDCB のリポジトリ直下には `LICENSE-Civetweb.md` しか無く、`Document/Readme.txt` と `Readme_Mod.txt` に再配布条件の記載は見つからなかった。
- EMWUI は GitHub がライセンスを検出しない。
- BonDriver_LinuxMirakc は MIT。

### F9. Docker Compose(5.5.1 で確認)

- `compose.override.yml` の `volumes` と `devices` は、`compose.yml` の定義に追加される。
- `ports: !override` で置き換えになる。
- `env_file` の `required: false` で、ファイルが無くてもエラーにならない。
- `depends_on` の `required: false` で、依存先のサービスが無効でも起動できる。
- プロジェクト名は、指定が無ければ `compose.yml` のあるフォルダの名前になる。`.env` の `COMPOSE_PROJECT_NAME` で変えられる(`docker compose config` の `name` で確認)。コンテナ、ネットワーク、`name:` の無いボリューム、ビルドしたイメージのタグ(`<プロジェクト名>-<サービス名>`)は、プロジェクト名で区別される。

## 未確認(担当フェーズで確認すること)

| # | 内容 | 確認するフェーズ | 確認方法 |
|---|---|---|---|
| ~~U1~~ | ~~EDCB が arm64 でビルドできるか~~ | 1 | **確認済み**(フェーズ 1、PR #15 の CI)。GitHub のネイティブ arm64 ランナー(`ubuntu-24.04-arm`、aarch64)で、パッチ込みのビルドと `-h` の確認が通った。`release.yml` は amd64 / arm64 のままでよい |
| ~~U2~~ | ~~EMWUI の固定コミットと EDCB `260904` の組み合わせで WebUI が動くか~~ | 1 | **確認済み**(フェーズ 1)。`/legacy/` と `/E3/` が 200。`/EMWUI/` は上流で削除された(F6) |
| U3 | `HttpPublic` 配下に実行時に書き込む処理があるか | 2 | `HttpPublic` 以下の Lua で書き込み先を調べる(`legacy/view.lua` と `xcode.lua` がログを書いている。書き込み先のパスを確認) |
| U4 | `HttpAccessControlList` の書式(IPv6、IPv4 射影アドレスの扱い) | 2 | `Document/Readme_Mod.txt` の該当節を読む |
| U5 | EDCB の ini のキー名は大文字小文字を区別するか | 2 | `Common/PathUtil.cpp` の `GetPrivateProfile*` の Linux 実装を読む |
| U6 | SIGTERM を受けた EpgTimerSrv / EpgDataCap_Bon が録画ファイルを正常に閉じるか、所要時間 | 2 | 終了処理のソースを読む。`stop_grace_period` の値の根拠にする |
| U7 | Linux 版の `ssl_cert.pem` の置き場所(`/var/local/edcb` か) | 2 | `civetweb` の初期化部分で証明書のパスを組み立てている箇所を読む |
| ~~U8~~ | ~~イメージに `libssl.so.3` が入っているか~~ | 2 | **確認済み**(フェーズ 1 のビルドで確認)。`libssl.so.3` と `libcrypto.so.3` が `/lib/x86_64-linux-gnu/` にある |
| U9 | Mirakurun の `/api/channels` と `/api/tuners` が、BonDriver と自動設定の前提どおりの形か | 3 | Mirakurun の API 定義を読む |
| U10 | 切断時に EDCB 側が再選局するか | 3 | `BonCtrl` の受信監視部分を読む。しないなら BonDriver 側に再接続を入れるかユーザに相談 |
| U11 | コマンドラインから `ReloadSetting` を呼ぶ手段 | 4 | `EpgTimerSrv` の制御コマンド、Lua API(`edcb.ReloadSetting`)を調べる |
| U12 | スキャンにかかる時間 | 4 | 実機確認をユーザに依頼 |
| U13 | 録画中か・直近の予約を取得する手段 | 4 | Legacy WebUI / EMWUI の API、Lua API を調べる |
| U14 | pcscd が polkit 有効でビルドされている場合の、root / 非 root クライアントの扱い | 5 | pcsc-lite の `auth.c` を読む |
