#!/usr/bin/env python3
"""
NotionDBの歯抜けレコードを調査するスクリプト

1. FitbitのmemberSince（最古データ日）を取得
2. memberSinceから本日までの全日付リストを生成
3. NotionDBに存在する日付を取得
4. 歯抜け（Notionに存在しない日付）を出力
"""

import os
import requests
from datetime import datetime, date, timedelta
from notion_client import Client
from token_store import load_tokens


def get_fitbit_member_since(access_token: str) -> date:
    """FitbitプロフィールからmemberSince（登録日）を取得"""
    headers = {'Authorization': f'Bearer {access_token}'}

    response = requests.get(
        'https://api.fitbit.com/1/user/-/profile.json', headers=headers
    )
    if response.status_code != 200:
        raise RuntimeError(f"Fitbit profile API failed: {response.text}")

    member_since = response.json()['user']['memberSince']
    return datetime.strptime(member_since, '%Y-%m-%d').date()


def get_notion_existing_dates(notion, database_id):
    """NotionDBに存在する全日付を取得"""
    existing_dates = set()
    cursor = None

    while True:
        kwargs = {
            'database_id': database_id,
            'filter': {
                'property': '日付',
                'date': {'is_not_empty': True}
            },
            'sorts': [{'property': '日付', 'direction': 'ascending'}],
            'page_size': 100,
        }
        if cursor:
            kwargs['start_cursor'] = cursor

        result = notion.databases.query(**kwargs)

        for page in result['results']:
            date_prop = page['properties'].get('日付', {}).get('date')
            if date_prop and date_prop.get('start'):
                existing_dates.add(date_prop['start'][:10])  # YYYY-MM-DD

        if not result.get('has_more'):
            break
        cursor = result['next_cursor']

    return existing_dates


def main():
    access_token, refresh_token = load_tokens()
    os.environ['FITBIT_ACCESS_TOKEN'] = access_token
    os.environ['FITBIT_REFRESH_TOKEN'] = refresh_token

    notion_token = os.getenv('NOTION_TOKEN')
    database_id = os.getenv('NOTION_DATABASE_ID')
    if not notion_token or not database_id:
        raise RuntimeError("NOTION_TOKEN / NOTION_DATABASE_ID が設定されていません")
    notion = Client(auth=notion_token)

    # 1. Fitbit最古日取得
    print("Fitbit memberSince を取得中...")
    member_since = get_fitbit_member_since(access_token)
    today = date.today()
    print(f"  memberSince : {member_since}")
    print(f"  本日        : {today}")
    print(f"  対象期間    : {(today - member_since).days + 1} 日間")
    print()

    # 2. 全日付リスト生成
    all_dates = set()
    d = member_since
    while d <= today:
        all_dates.add(d.strftime('%Y-%m-%d'))
        d += timedelta(days=1)

    # 3. Notion既存日付取得
    print("NotionDBの既存レコードを取得中...")
    existing_dates = get_notion_existing_dates(notion, database_id)
    print(f"  Notionに存在するレコード数: {len(existing_dates)} 件")
    print()

    # 4. 歯抜け算出
    missing_dates = sorted(all_dates - existing_dates)

    if not missing_dates:
        print("歯抜けなし。全データが揃っています。")
        return

    print(f"歯抜けレコード: {len(missing_dates)} 件")
    print("-" * 30)

    # 連続した期間をまとめて表示
    ranges = []
    start = missing_dates[0]
    prev = missing_dates[0]
    for d in missing_dates[1:]:
        curr = datetime.strptime(d, '%Y-%m-%d').date()
        prev_date = datetime.strptime(prev, '%Y-%m-%d').date()
        if (curr - prev_date).days == 1:
            prev = d
        else:
            ranges.append((start, prev))
            start = d
            prev = d
    ranges.append((start, prev))

    for s, e in ranges:
        if s == e:
            print(f"  {s}")
        else:
            days = (datetime.strptime(e, '%Y-%m-%d') - datetime.strptime(s, '%Y-%m-%d')).days + 1
            print(f"  {s} 〜 {e}  ({days}日間)")

    print()
    print("バックフィルするには:")
    print(f"  python backfill_fitbit_data.py --start-date {missing_dates[0]} --end-date {missing_dates[-1]}")


if __name__ == "__main__":
    main()
