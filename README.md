よくまとまっています。今回の変更点を反映して更新します。
# Fitbit to Notion Health Data Sync

> このプロジェクトは [radusqrt/fitbit-notion-sync](https://github.com/radusqrt/fitbit-notion-sync) をベースに、日本語対応、栄養データ同期、GitHub Secrets自動更新などのカスタマイズを行ったものです。

## 概要

Fitbit APIからヘルスデータを取得し、Notion APIを通じてNotionデータベースに書き込みます。GitHub Actionsによる10分間隔のスケジュール実行で、設定後は完全自動で動作します。

Fitbit OAuthのリフレッシュトークンは使い捨て（one-time use）であるため、トークンリフレッシュ時に新しいトークンペアをGitHub Secretsへ自動的に書き戻す仕組みを実装しています。これにより、手動でのトークン更新は不要です。

### 同期されるデータ

**アクティビティ:** 歩数、距離 (km)、消費カロリー (kcal)、アクティブ時間 (分)

**睡眠:** 睡眠時間、睡眠効率、深い睡眠・浅い睡眠・レム睡眠 (分)、就寝時刻、起床時刻

**心拍:** 安静時心拍数 (bpm)、脂肪燃焼ゾーン・有酸素ゾーン・ピークゾーン (分)

**HRV:** 日次RMSSD (ms)、深睡眠RMSSD (ms)

**体組成:** 体重 (kg)、BMI、体脂肪率 (%)

**栄養 (Fitbitアプリでの食事ログ):** 摂取カロリー (kcal)、炭水化物 (g)、脂質 (g)、たんぱく質 (g)、食物繊維 (g)、ナトリウム (g)

## 必要なアカウント

- GitHubアカウント（無料）
- Fitbitアカウント（Pixel Watch利用者は既に所持）
- Notionアカウント（無料）

## セットアップ

### 1. Fitbit APIアプリの作成

https://dev.fitbit.com/apps/new にアクセスし、以下の設定でアプリを登録します。

- **OAuth 2.0 Application Type:** Server
- **Redirect URL:** http://localhost:8080

登録後に発行される Client ID と Client Secret をメモしてください。

### 2. Notion側の準備

#### インテグレーションの作成

https://www.notion.so/my-integrations にアクセスし、新しいインテグレーションを作成します。作成後に表示される Internal Integration Token（`secret_` で始まる文字列）をメモしてください。

#### データベースの作成

Notionで新しいデータベース（テーブルビュー）を作成します。プロパティの追加は `update_notion_schema.py` で自動的に行えます。

#### インテグレーションとの接続

作成したデータベースの「...」メニューから「コネクトを追加」を選び、作成したインテグレーションを接続してください。

#### データベースIDの取得

データベースをブラウザで開き、URLの中の32文字の英数字部分がDatabase IDです。

```
https://www.notion.so/ワークスペース名/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=yyyyyyyy
                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                      この部分がDatabase ID
```

### 3. Fitbit OAuthトークンの取得

以下のURLの `YOUR_CLIENT_ID` を自分のClient IDに置き換えてブラウザでアクセスします。

```
https://www.fitbit.com/oauth2/authorize?response_type=code&client_id=YOUR_CLIENT_ID&redirect_uri=http%3A%2F%2Flocalhost%3A8080&scope=activity+heartrate+sleep+weight+profile+nutrition&expires_in=31536000
```

認可後、ブラウザのURLバーに表示される `code=` と `#` の間の文字列をコピーし、以下のcurlコマンドを実行します。

```bash
curl -X POST https://api.fitbit.com/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "YOUR_CLIENT_ID:YOUR_CLIENT_SECRET" \
  -d "grant_type=authorization_code" \
  -d "code=COPIED_CODE" \
  -d "redirect_uri=http://localhost:8080"
```

レスポンスに含まれる `access_token` と `refresh_token` をメモしてください。

### 4. GitHub Personal Access Token (PAT) の発行

GitHub Actionsでトークンリフレッシュ後にGitHub Secretsを自動更新するために必要です。

GitHub の Settings（アカウント設定） > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token から作成します。

- **Token name:** 任意（例: fitbit-sync-token-updater）
- **Expiration:** No expiration を推奨
- **Repository access:** Only select repositories で対象リポジトリを選択
- **Permissions:** Repository permissions > Secrets > Read and write

生成されたトークン（`github_pat_` で始まる文字列）をメモしてください。

### 5. 環境変数の設定

#### ローカル実行用

プロジェクトルートに `.env` ファイルを作成します。

```
FITBIT_CLIENT_ID=your_client_id
FITBIT_CLIENT_SECRET=your_client_secret
FITBIT_ACCESS_TOKEN=your_access_token
FITBIT_REFRESH_TOKEN=your_refresh_token
NOTION_TOKEN=your_notion_token
NOTION_DATABASE_ID=your_database_id
```

#### GitHub Actions用

リポジトリの Settings > Secrets and variables > Actions > New repository secret から、以下の7つの値を登録します。

| Secret名             | 内容                             |
| -------------------- | -------------------------------- |
| FITBIT_CLIENT_ID     | Fitbit APIのClient ID            |
| FITBIT_CLIENT_SECRET | Fitbit APIのClient Secret        |
| FITBIT_ACCESS_TOKEN  | Fitbit OAuthアクセストークン     |
| FITBIT_REFRESH_TOKEN | Fitbit OAuthリフレッシュトークン |
| NOTION_TOKEN         | NotionインテグレーションToken    |
| NOTION_DATABASE_ID   | NotionデータベースID             |
| PAT_TOKEN            | GitHub Personal Access Token     |

### 6. Notionデータベースのスキーマ設定

以下のコマンドで必要なプロパティが自動的にデータベースに追加されます。

```bash
python update_notion_schema.py
```

### 7. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

## 使い方

### 自動同期（GitHub Actions）

設定完了後、GitHub Actionsが10分ごとに自動実行され、当日と前日のデータをNotionに同期します。前日のデータも同期する理由は、深夜に確定する睡眠データなどを確実に取り込むためです。

GitHub Actions画面から手動実行（Run workflow）も可能です。

同じ日付のデータは上書き更新されるため、複数回実行しても行が重複することはありません。

Fitbitのアクセストークンが期限切れになった場合、リフレッシュトークンで自動更新し、新しいトークンペアをGitHub Secretsに書き戻します。これにより次回以降の実行も正常に動作し続けます。

### 手動同期（ローカル）

```bash
# 当日のデータを同期
python manual_sync_today.py
```

### 過去データの一括取り込み

```bash
# Notionの最も古いエントリから指定日まで自動で遡って取り込み
python auto_backfill.py --target-start 2021-01-01

# 期間を指定して取り込み
python backfill_fitbit_data.py --start-date 2024-01-01 --end-date 2024-12-31

# 直近7日分を取り込み
python backfill_fitbit_data.py --last-week
```

`auto_backfill.py` はNotionデータベースの最も古い日付を自動検出し、そこから指定した開始日まで遡ります。途中で中断しても、再実行すれば続きから自動で再開します。

大量の過去データを取り込む場合は、Macのスリープを防止してから実行してください。

```bash
# 別ターミナルで実行（完了後 Ctrl+C で停止）
caffeinate -i
```

## ファイル構成

| ファイル                                 | 説明                                           |
| ---------------------------------------- | ---------------------------------------------- |
| `sync_fitbit_notion.py`                  | メイン同期スクリプト（GitHub Actionsから実行） |
| `manual_sync_today.py`                   | ローカルでの手動同期用                         |
| `auto_backfill.py`                       | Notionの最古エントリから自動バックフィル       |
| `backfill_fitbit_data.py`                | 期間指定での過去データ取り込み                 |
| `update_notion_schema.py`                | Notionデータベースのプロパティ自動追加         |
| `oauth_helper.py`                        | Fitbit OAuthトークンのリフレッシュ             |
| `.github/workflows/sync-health-data.yml` | GitHub Actionsワークフロー定義                 |

## Fitbit OAuthトークンの仕組み

Fitbitのアクセストークンは8時間で期限切れになります。期限切れ時にはリフレッシュトークンを使って新しいアクセストークンを取得しますが、Fitbit APIではリフレッシュトークンが使い捨て（one-time use）であり、リフレッシュのたびに新しいリフレッシュトークンも発行されます。古いリフレッシュトークンはその時点で無効化されます。

このため、GitHub Actions上でリフレッシュが発生した際には `gh secret set` コマンドを使って新しいトークンペアをGitHub Secretsに自動書き戻しています。この機能にはPAT_TOKENが必要です。

ローカル実行時は `.env` ファイルに新しいトークンが自動的に書き込まれます。

## Fitbit APIのレート制限

Fitbit APIには1時間あたり150リクエストの上限があります。1回の同期で14リクエスト（当日+前日の各7エンドポイント）を消費するため、10分間隔での自動実行は上限内に収まります。

過去データのバックフィル時は、スクリプト内で自動的にAPIコール間に遅延を挿入し、レート制限に引っかかった場合は自動リトライを行います。

## トラブルシューティング

**データが同期されない場合:** Pixel WatchからFitbitアプリへの同期が完了しているか確認してください。Fitbitアプリに最新データが反映されていればAPI側は問題ありません。

**トークンエラーが出る場合:** 通常はリフレッシュトークンで自動更新されますが、長期間使用しなかった場合やリフレッシュトークンが何らかの理由で無効化された場合は、STEP 3のOAuth認証を再実行し、`.env` とGitHub Secretsの FITBIT_ACCESS_TOKEN および FITBIT_REFRESH_TOKEN を更新してください。

**Notionにデータが入らない場合:** データベースIDが正しいか、インテグレーションがデータベースに接続されているか確認してください。

**栄養データが取得できない場合:** OAuthの認可時に `nutrition` スコープが含まれている必要があります。含まれていない場合はトークンを再取得してください。

**GitHub Actionsが失敗する場合:** リポジトリの Settings > Secrets and variables > Actions に7つのSecret（PAT_TOKEN含む）がすべて登録されているか確認してください。

## ライセンス

MIT License