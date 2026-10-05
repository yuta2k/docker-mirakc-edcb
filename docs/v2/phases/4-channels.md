# フェーズ 4: チャンネル定義の自動化

## 目的

チャンネルスキャンと、地上波用 / 衛星用への分割を自動化する。臨時の再スキャンを 1 コマンドでできるようにする。

関連する方針: `decisions.md` の D2、E1〜E3。仕様: `design.md` の 8、9 章。

## 先に確認すること

`facts.md` の U11、U13 を確認する。

## 作業

### 1. 分割の処理

- スキャン結果の ChSet4 と `/api/channels` から、種別ごとの ChSet4 を作る(`design.md` の 8.3)。
- space の求め方は、BonDriver の `InitChannel`(`facts.md` の F4)と**同じ規則**にする。同じ `type` が連続する区間ごとに space を 1 つ割り当てる。`GR, BS, GR` のように同じ種類が離れて現れる入力でも、BonDriver と同じ結果になること。
- ChSet4 の読み書きは、タブ区切り、UTF-8(BOM 付き)。列の意味は `facts.md` の F3。

### 2. スキャンの実行

- `design.md` の 8.1、8.2。
- スキャンは時間がかかる。進行状況が分かるよう、`EpgDataCap_Bon` の出力をそのまま標準出力に流す。
- スキャンが失敗、または結果が 0 件だったときは、既存のファイルを変えずに警告を出す。

### 3. ずれの検知

`design.md` の 8.4。

### 4. edcbctl

`design.md` の 9 章の `chscan` と `status`。

- `chscan --rebuild` で ChSet5 のフラグを引き継ぐ処理は、ChSet5 の列の意味を EDCB のソース(`Common/ParseTextInstances.cpp` の ChSet5 の読み書き)で確認してから実装する。
- `status` は、U13 で手段が見つからなければ実装せず、実施記録に理由を書く。

### 5. テスト

- 分割は、固定のスキャン結果と `/api/channels` の組を数パターン用意して pytest で確認する。少なくとも次を含める。
  - 地上波のみ / 衛星のみ / 両方
  - 同じ種類が離れて現れる並び
  - 現在の `edcb/ini/Setting/BonDriver_LinuxMirakc(LinuxMirakc).ChSet4.txt` をコピーしたもの(実データ。**リポジトリには入れない**。チャンネル構成は利用者の環境情報なので、テスト用の固定データは内容を書き換えた合成データにする)
- スキャンそのものは CI では試せない。`EpgDataCap_Bon` を差し替えられる作りにして、スキャン結果を置くだけの偽コマンドでテストする。

## 受け入れ条件

- [ ] 分割のテストがすべて通る。T の行は地上波の space だけ、S の行は衛星の space だけになり、space と ch の値は元と同じ
- [ ] 本数が 0 の種別の ChSet4 は作られない。以前に自分が生成したものは削除される
- [ ] 利用者が置いた ChSet4(状態ファイルに記録が無いもの)は、上書きも削除もされない
- [ ] `ChSet5.txt` が無い状態で起動すると、スキャンが実行される(偽コマンドで確認)
- [ ] `ChSet5.txt` がある状態では、起動時にスキャンが実行されない
- [ ] `EDCB_CHSCAN=never` では、どの場合もスキャンが実行されない
- [ ] `/api/channels` の内容を変えて再起動すると、ずれの警告が出る。ファイルは変わらない
- [ ] `edcbctl chscan <名前>` で、その接続先だけが再スキャン・再分割される
- [ ] `edcbctl chscan --all --rebuild` で、ChSet5 が退避されてから作り直され、フラグが引き継がれる
- [ ] 既存の利用者のデータ(従来の ChSet4 / ChSet5 がある状態)で起動しても、チャンネル定義のファイルが 1 つも変わらない

## 実機確認の依頼

次の手順をまとめて、ユーザに依頼する。**実データを使う確認なので、退避を取ってから行うよう手順に書くこと。**

- 空の設定ディレクトリで起動し、スキャンが完走するか。かかった時間(U12)
- 生成された `_T` / `_S` の ChSet4 で、地上波と衛星がそれぞれ録画できるか
- `edcbctl chscan` のあと、EpgTimerSrv に反映されるか(再起動が要るか)

## 実施記録

### 先に確認したこと

- U11: 手段はある(制御コマンド `CMD2_EPG_SRV_RELOAD_SETTING`、Lua の `edcb.ReloadSetting`)が、ChSet5 しか読み直さない。ChSet4 と BonDriver の一覧は起動時にしか読まないので、`edcbctl chscan` のあとは再起動を案内する(`facts.md` の U11、F17)。
- U13: EpgTimerSrv の制御用 UNIX ソケット(`/var/local/edcb/EpgTimerSrvPipe`)に、チューナーの状態と予約一覧を問い合わせられる。`edcbctl status` を実装した(F17)。
- スキャンの動きを EDCB のソースで確かめた(F16)。設計に影響した点が 2 つある。
  - EDCB はスキャン結果を `Setting/` の ChSet4 へ直接上書きする。→ 別名の BonDriver でスキャンする(`design.md` の 8.1)。
  - EDCB はスキャンのたびに、見つけたサービスの ChSet5 のフラグ(EPG 取得対象、検索対象)を既定に戻す。→ `--rebuild` に限らず、スキャンのたびにフラグを書き戻す。
- ChSet5 の列の意味は `CParseChText5::ParseLine` / `SaveLine` で確かめた(F16)。

### 行ったこと

- `edcb_provision/chset.py`: ChSet4 / ChSet5 の読み書き、space の割り当て(BonDriver の `InitChannel` と同じ規則)、分割、フラグの書き戻し、`/api/channels` のハッシュ。
- `edcb_provision/channels.py`: スキャン(別名の BonDriver、`PUID` / `PGID` での実行、出力の転送、時間切れ、失敗時の ChSet5 の復元)、起動時の処理(8.2〜8.4)、分割の反映、`edcbctl chscan`。
- `edcb_provision/ctrlcmd.py`: EpgTimerSrv の制御コマンドの小さなクライアントと `edcbctl status`。
- `edcbctl backends` の「channel scan」の行(スキャンの日時、ずれの有無、利用者のファイル)。
- ヘルスチェック: 初回のスキャン中(`EpgDataCap_Bon -chscan` が動いている間)は正常とする。初回のスキャンは開始猶予の 2 分より長くかかりうるため。
- テスト: `test_chset.py`(分割。地上波のみ、衛星のみ、両方、同じ種類が離れて現れる並び、SKY、CRLF、実データ)、`test_channels.py`(偽の `EpgDataCap_Bon` を使った起動時の処理と `chscan`)、`test_ctrlcmd.py`(偽の制御用ソケット)。偽の `EpgDataCap_Bon`(`edcb/tests/fake_epgdatacap.py`)は、BonDriver の ini が指す偽の Mirakurun から `/api/channels` を取り、BonDriver と同じ規則で space を振った ChSet4 を書き、EDCB と同じように ChSet5 へ足す(フラグも既定に戻す)。差し替えは環境変数 `EDCB_PROVISION_EPGDATACAP`(テスト専用)。
- 偽の Mirakurun にシナリオ `interleaved`(GR、BS、GR、CS の並び)と `split-interleaved`(`split` のチューナーで `interleaved` のチャンネル)を足した。
- 結合テスト `tests/integration/phase4.sh`(T40〜T48)。`phase3.sh` の T31、T35、T39 は `EDCB_CHSCAN=never` にした(偽サーバを初回にスキャンしてしまうため)。
- `edcb.env-sample` に `EDCB_CHSCAN` と `edcbctl chscan` / `status` の説明を足した。

### 設計から変えた点・決めた点

`design.md` の 8、9、10 章に「フェーズ 4 で決めた点」として書き足した。要点:

- 別名の BonDriver(`BonDriver_LinuxMirakc-scan-<名前>.so`)でスキャンする。
- ChSet5 のフラグは、`--rebuild` に限らずスキャンのたびに書き戻す。
- `--rebuild` は、1 つでも失敗したら ChSet5 を元に戻し、どの結果も使わない。
- `edcbctl chscan --force` を足した。利用者が置いた ChSet4 を、退避してから引き取る(v1 からの移行用)。`--force` が無いときは、そのような接続先のスキャンを断る。
- `ChSet5.txt` が無いときは、前にスキャンした接続先もスキャンし直す。
- `EDCB_CHSCAN=never` のときは、スキャンの無い接続先の警告を出さない。
- 分割は起動のたびに保存済みのスキャン結果から行う(チューナー数の変化に追従する)。
- `status` は録画中のとき終了コードを変えない(問い合わせの成否だけを返す)。録画中かは出力の `recording:` の行で分かる。

### 検証

- `scripts/check.sh`: すべて PASS(pytest 157 件、1 件 SKIP は下の実データのテスト)。
- 実データの分割(`test_chset.py` の `test_split_real_data`。`EDCB_TEST_CHSET4` と `EDCB_TEST_BACKEND_JSON` に、この環境の `edcb/ini/` のファイルを指定して手元で実行。ファイルはリポジトリに入れていない): PASS。169 行が T 46 行、S 123 行に分かれ、M は元のファイルとバイト単位で一致した。
- `tests/integration/run.sh`(ユーザが実行):
  - 1 回目(ビルドあり、`4edf1f4`): pass=30 fail=3。
    - T43、T48 が FAIL。`edcbctl status` が送るチューナーの状態の取得コマンドの番号を誤っていた。EDCB のソースの行番号(2208)を値と取り違えており、正しくは `CtrlCmdDef.h` の 1066。EpgTimerSrv は 203(未対応)を返した。pytest の偽のソケットも同じ定数を使っていたので気づけなかった。直した。T43 のうち、スキャンと分割、分割したファイルでの選局(`GR/26`)は通っている。
    - T30(フェーズ 3)が FAIL。BonDriver のビルドの段がキャッシュから使われ、パッチを当てたときの出力(`Applied 3 patch(es)`)がビルドのログに出なかった。テストの不備。出力が無いときは、イメージ内の `.so` に再接続のパッチ(0003)が足す文字列があるかで確かめるようにした。
    - ほかは PASS。T40 では、分割したファイルの行を `_VM_S` / `_T` の BonDriver で選局し、偽サーバに `BS/BS01_0`、`CS/CS2`、`GR/26` のストリームが要求された。T46 は実データ(この環境の ChSet4 / ChSet5 のコピー)で、ファイルは変わらなかった。T47 は本物の `EpgDataCap_Bon` が 5 チャンネルすべてを選局し、サービスが見つからないのでファイルを変えずに警告した(起動まで 13 秒、`ChChgTimeOut=2`)。
  - 2 回目: 修正後に依頼中。

### 受け入れ条件の状況

| 条件 | 状況 |
|---|---|
| 分割のテスト(T は地上波、S は衛星、space と ch は元と同じ) | 確認(pytest。結合テストの T40 で、分割したファイルの行を BonDriver で選局して確かめる予定) |
| 本数 0 の種別は作らない。以前の生成物は削除 | 確認(pytest) |
| 利用者が置いた ChSet4 は上書きも削除もされない | 確認(pytest)。結合テストは T46 |
| `ChSet5.txt` が無い状態で起動するとスキャン | 確認(pytest)。結合テストは T40、T47(本物の `EpgDataCap_Bon`) |
| `ChSet5.txt` がある状態ではスキャンしない | 確認(pytest)。結合テストは T41 |
| `EDCB_CHSCAN=never` ではスキャンしない | 確認(pytest)。結合テストは T45 |
| `/api/channels` を変えて再起動すると警告、ファイルは不変 | 確認(pytest)。結合テストは T42 |
| `edcbctl chscan <名前>` でその接続先だけ | 確認(pytest)。結合テストは T43 |
| `edcbctl chscan --all --rebuild` で退避、作り直し、フラグ引き継ぎ | 確認(pytest)。結合テストは T44 |
| 既存の利用者のデータで起動してもファイルが変わらない | 確認(pytest)。結合テストは T46 |

### 実機確認の依頼(未実施)

上の「実機確認の依頼」の 3 点は、結合テストのあとでユーザに依頼する。手順は次のとおり(実データを使うので、先に `./edcb/ini` を退避する)。

1. 稼働中の構成とは別のディレクトリ・別のプロジェクト名(`COMPOSE_PROJECT_NAME`)・別のポートで、空の `./edcb/ini` から起動する。`docker compose logs -f edcb` で `chscan` の進行を見て、`backend <名前>: the scan found N service(s) in S s` の秒数を記録する(U12)。
2. `_T` / `_S` の BonDriver で、地上波と衛星をそれぞれ録画する(WebUI でチューナーを固定した予約を入れる)。
3. `docker compose exec edcb edcbctl chscan <名前>` のあと、再起動の前と後で EpgTimerSrv の表示(WebUI のチャンネル一覧)が変わるかを見る。
