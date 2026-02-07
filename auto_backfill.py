#!/usr/bin/env python3
"""
Auto backfill: fetch the oldest date in Notion DB and backfill from a target start date
"""

import os
import argparse
from datetime import datetime, timedelta
from notion_client import Client
from dotenv import load_dotenv
from backfill_fitbit_data import get_fitbit_data, update_notion_database, generate_date_list
import time


def get_oldest_date_in_notion():
    """Get the oldest date entry in the Notion database"""
    load_dotenv()

    notion = Client(auth=os.getenv('NOTION_TOKEN'))
    database_id = os.getenv('NOTION_DATABASE_ID')

    # Query with ascending sort on date, limit 1
    result = notion.databases.query(
        database_id=database_id,
        sorts=[
            {
                "property": "日付",
                "direction": "ascending"
            }
        ],
        page_size=1
    )

    if result['results']:
        oldest_page = result['results'][0]
        date_prop = oldest_page['properties']['日付']['date']
        if date_prop and date_prop.get('start'):
            return date_prop['start']

    return None


def main():
    parser = argparse.ArgumentParser(
        description='Auto backfill from oldest Notion entry')
    parser.add_argument('--target-start', '-t', type=str, default='2021-01-01',
                        help='Target start date to backfill to (default: 2021-01-01)')
    parser.add_argument('--batch-size', '-b', type=int, default=None,
                        help='Max number of days to process in this run (default: unlimited)')

    args = parser.parse_args()

    print("🔄 Auto Backfill: Checking Notion database...")

    oldest_date = get_oldest_date_in_notion()

    if not oldest_date:
        print("❌ No entries found in Notion database")
        print("   Run manual_sync_today.py first")
        return

    print(f"📅 Oldest entry in Notion: {oldest_date}")

    # Calculate backfill range: from target start to 1 day before oldest
    end_date = (datetime.strptime(oldest_date, '%Y-%m-%d') -
                timedelta(days=1)).strftime('%Y-%m-%d')
    start_date = args.target_start

    if start_date > end_date:
        print(
            f"✅ No backfill needed. Oldest entry ({oldest_date}) is already at or before target ({start_date})")
        return

    dates = generate_date_list(start_date, end_date)
    total_days = len(dates)

    if args.batch_size:
        # Process from most recent to oldest (reverse order) with batch limit
        dates = list(reversed(dates))[:args.batch_size]
        dates = list(reversed(dates))
        print(
            f"📊 Backfill range: {dates[0]} to {dates[-1]} ({len(dates)} days, batch limited)")
    else:
        print(
            f"📊 Backfill range: {start_date} to {end_date} ({total_days} days)")

    # ~19 sec per day (7 API calls * 2s + 5s delay)
    estimated_hours = (total_days * 19) / 3600
    print(f"⏱️  Estimated time: {estimated_hours:.1f} hours")
    print()

    created = 0
    updated = 0
    errors = 0

    for date in dates:
        print(f"📅 Processing {date}...")

        fitbit_data = get_fitbit_data(date)
        if not fitbit_data:
            print(f"❌ Failed to fetch Fitbit data for {date}")
            errors += 1
            continue

        print(f"   Steps: {fitbit_data.get('steps', 0)}, Sleep: {fitbit_data.get('sleep_hours', 0)}h, HRV: {fitbit_data.get('hrv_daily_rmssd', 'N/A')}")

        result = update_notion_database(date, fitbit_data)
        if result == "created":
            print(f"✅ Created entry for {date}")
            created += 1
        elif result == "updated":
            print(f"✅ Updated entry for {date}")
            updated += 1
        else:
            errors += 1

        if date != dates[-1]:
            time.sleep(5)

    print(f"\n🎉 Backfill completed!")
    print(f"📊 Results: {created} created, {updated} updated, {errors} errors")

    # Show remaining
    if args.batch_size and len(dates) < total_days:
        remaining = total_days - len(dates)
        print(f"📋 Remaining: {remaining} days. Run again to continue.")


if __name__ == "__main__":
    main()
