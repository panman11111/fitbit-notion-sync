#!/usr/bin/env python3
"""
Sync Fitbit data to Notion database
Fetches yesterday's and today's health metrics and updates Notion
"""

import os
import subprocess
import requests
from datetime import datetime, timedelta
from notion_client import Client
from dotenv import load_dotenv

# --- Gemini API / Google Drive food photo tracking (disabled) ---
# If you want to re-enable this feature, uncomment the following block
# and configure Google Drive / Gemini API credentials in .env
#
# try:
#     from google_drive_food import process_drive_food_photos, format_meal_text
#     GOOGLE_DRIVE_AVAILABLE = True
# except ImportError as e:
#     print(f"Google Drive integration not available: {e}")
#     GOOGLE_DRIVE_AVAILABLE = False
#     def process_drive_food_photos(date):
#         return None
#     def format_meal_text(foods):
#         return ""
# ---


def get_yesterday_date():
    """Get yesterday's date in YYYY-MM-DD format"""
    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime('%Y-%m-%d')


def update_github_secret(secret_name, secret_value, max_retries=3):
    """Update a GitHub Actions repository secret via gh CLI with retry"""
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            result = subprocess.run(
                ['gh', 'secret', 'set', secret_name, '--body', secret_value],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                print(f"  GitHub Secret '{secret_name}' updated successfully")
                return
            last_error = result.stderr.strip()
            print(f"  Attempt {attempt}/{max_retries} failed for '{secret_name}': {last_error}")
        except FileNotFoundError:
            raise RuntimeError("gh CLI not found. Cannot persist tokens to GitHub Secrets.")
        except Exception as e:
            last_error = str(e)
            print(f"  Attempt {attempt}/{max_retries} error for '{secret_name}': {last_error}")

        if attempt < max_retries:
            import time
            time.sleep(2 ** attempt)

    raise RuntimeError(
        f"Failed to update GitHub Secret '{secret_name}' after {max_retries} attempts: {last_error}"
    )


def refresh_fitbit_token():
    """Refresh the Fitbit access token if needed"""
    load_dotenv()

    client_id = os.getenv('FITBIT_CLIENT_ID')
    client_secret = os.getenv('FITBIT_CLIENT_SECRET')
    refresh_token = os.getenv('FITBIT_REFRESH_TOKEN')

    import base64
    credentials = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    headers = {
        'Authorization': f'Basic {credentials}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }

    response = requests.post(
        'https://api.fitbit.com/oauth2/token', data=data, headers=headers)

    if response.status_code == 200:
        tokens = response.json()
        new_access_token = tokens['access_token']
        new_refresh_token = tokens['refresh_token']

        # Update .env file if it exists (local environment)
        if os.path.exists('.env'):
            with open('.env', 'r') as f:
                content = f.read()

            content = content.replace(
                f'FITBIT_ACCESS_TOKEN={os.getenv("FITBIT_ACCESS_TOKEN")}',
                f'FITBIT_ACCESS_TOKEN={new_access_token}'
            )
            content = content.replace(
                f'FITBIT_REFRESH_TOKEN={refresh_token}',
                f'FITBIT_REFRESH_TOKEN={new_refresh_token}'
            )

            with open('.env', 'w') as f:
                f.write(content)

        # Update environment variables in memory
        os.environ['FITBIT_ACCESS_TOKEN'] = new_access_token
        os.environ['FITBIT_REFRESH_TOKEN'] = new_refresh_token

        # GitHub Actions: persist new tokens to Secrets for next run
        if os.environ.get('GITHUB_ACTIONS') == 'true':
            print("  Updating GitHub Secrets with new tokens...")
            update_github_secret('FITBIT_ACCESS_TOKEN', new_access_token)
            update_github_secret('FITBIT_REFRESH_TOKEN', new_refresh_token)

        return new_access_token
    else:
        raise Exception(f"Failed to refresh token: {response.text}")


def make_api_request_with_refresh(url, headers):
    """Make API request with automatic token refresh if needed"""
    response = requests.get(url, headers=headers)

    if response.status_code == 401:  # Token expired
        print("  Access token expired, refreshing...")
        new_token = refresh_fitbit_token()  # RuntimeError は呼び出し元に伝播させる
        headers['Authorization'] = f'Bearer {new_token}'
        response = requests.get(url, headers=headers)

    return response


def get_fitbit_data(date):
    """Fetch comprehensive Fitbit data for a specific date"""
    load_dotenv()
    access_token = os.getenv('FITBIT_ACCESS_TOKEN')

    headers = {'Authorization': f'Bearer {access_token}'}
    base_url = 'https://api.fitbit.com/1/user/-'

    data = {}

    try:
        # Activity summary
        response = make_api_request_with_refresh(
            f'{base_url}/activities/date/{date}.json', headers)
        if response.status_code == 200:
            activities = response.json()
            summary = activities['summary']
            data['steps'] = summary.get('steps', 0)
            data['distance'] = summary.get('distances', [{}])[0].get(
                'distance', 0) if summary.get('distances') else 0
            data['calories'] = summary.get('caloriesOut', 0)
            data['active_minutes'] = summary.get(
                'fairlyActiveMinutes', 0) + summary.get('veryActiveMinutes', 0)

        # Sleep data with detailed stages
        headers_v12 = headers.copy()
        headers_v12['Accept-Language'] = 'en_US'
        headers_v12['Accept-Version'] = '1.2'

        next_day = (datetime.strptime(date, '%Y-%m-%d') +
                    timedelta(days=1)).strftime('%Y-%m-%d')
        response = make_api_request_with_refresh(
            f'https://api.fitbit.com/1.2/user/-/sleep/list.json?beforeDate={next_day}&sort=desc&limit=5', headers_v12)
        if response.status_code == 200:
            sleep_data = response.json()
            if sleep_data.get('sleep'):
                main_sleep = None
                for sleep_session in sleep_data['sleep']:
                    if sleep_session.get('dateOfSleep') == date and sleep_session.get('isMainSleep', False):
                        main_sleep = sleep_session
                        break

                if not main_sleep:
                    for sleep_session in sleep_data['sleep']:
                        if sleep_session.get('dateOfSleep') == date:
                            main_sleep = sleep_session
                            break

                if main_sleep:
                    data['sleep_hours'] = round(
                        main_sleep.get('minutesAsleep', 0) / 60, 1)
                    data['sleep_efficiency'] = main_sleep.get('efficiency', 0)
                    data['sleep_start'] = main_sleep.get('startTime', '')
                    data['sleep_end'] = main_sleep.get('endTime', '')

                    levels = main_sleep.get('levels', {})

                    if 'summary' in levels and levels['summary']:
                        summary = levels['summary']
                        data['deep_sleep'] = summary.get(
                            'deep', {}).get('minutes', 0)
                        data['light_sleep'] = summary.get(
                            'light', {}).get('minutes', 0)
                        data['rem_sleep'] = summary.get(
                            'rem', {}).get('minutes', 0)

                    elif 'data' in levels and levels['data']:
                        stage_minutes = {'deep': 0, 'light': 0, 'rem': 0}

                        for period in levels['data']:
                            stage = period.get('level', '')
                            if stage in stage_minutes:
                                duration_seconds = period.get('seconds', 0)
                                stage_minutes[stage] += duration_seconds // 60

                        if 'shortData' in levels:
                            for period in levels.get('shortData', []):
                                stage = period.get('level', '')
                                if stage in stage_minutes:
                                    duration_seconds = period.get('seconds', 0)
                                    stage_minutes[stage] += duration_seconds // 60

                        data['deep_sleep'] = stage_minutes['deep']
                        data['light_sleep'] = stage_minutes['light']
                        data['rem_sleep'] = stage_minutes['rem']

                    else:
                        minute_data = main_sleep.get('minuteData', [])
                        if minute_data:
                            asleep_minutes = sum(
                                1 for m in minute_data if m.get('value') == '1')
                            data['light_sleep'] = asleep_minutes
                            data['deep_sleep'] = 0
                            data['rem_sleep'] = 0
                        else:
                            data['deep_sleep'] = 0
                            data['light_sleep'] = 0
                            data['rem_sleep'] = 0

        # Heart rate data (resting + zones)
        response = make_api_request_with_refresh(
            f'{base_url}/activities/heart/date/{date}/1d.json', headers)
        if response.status_code == 200:
            hr_data = response.json()
            if hr_data.get('activities-heart'):
                heart_info = hr_data['activities-heart'][0].get('value', {})
                data['resting_heart_rate'] = heart_info.get('restingHeartRate')

                zones = heart_info.get('heartRateZones', [])
                for zone in zones:
                    zone_name = zone.get('name', '').lower().replace(' ', '_')
                    if 'fat_burn' in zone_name or 'fat burn' in zone_name:
                        data['fat_burn_minutes'] = zone.get('minutes', 0)
                    elif 'cardio' in zone_name:
                        data['cardio_minutes'] = zone.get('minutes', 0)
                    elif 'peak' in zone_name:
                        data['peak_minutes'] = zone.get('minutes', 0)

        # Weight data (if available)
        response = make_api_request_with_refresh(
            f'{base_url}/body/log/weight/date/{date}.json', headers)
        if response.status_code == 200:
            weight_data = response.json()
            if weight_data.get('weight'):
                latest_weight = weight_data['weight'][0]
                data['weight'] = latest_weight.get('weight')
                data['bmi'] = latest_weight.get('bmi')

        # Body fat data (if available)
        response = make_api_request_with_refresh(
            f'{base_url}/body/log/fat/date/{date}.json', headers)
        if response.status_code == 200:
            fat_data = response.json()
            if fat_data.get('fat'):
                data['body_fat'] = fat_data['fat'][0].get('fat')

        # HRV data (Heart Rate Variability)
        response = make_api_request_with_refresh(
            f'{base_url}/hrv/date/{date}.json', headers)
        if response.status_code == 200:
            hrv_data = response.json()
            if hrv_data.get('hrv'):
                hrv_entries = hrv_data['hrv']
                if hrv_entries:
                    latest_hrv = hrv_entries[-1]
                    hrv_value = latest_hrv.get('value', {})
                    data['hrv_daily_rmssd'] = hrv_value.get('dailyRmssd')
                    data['hrv_deep_rmssd'] = hrv_value.get('deepRmssd')

        # Nutrition data (food logging from Fitbit app)
        response = make_api_request_with_refresh(
            f'{base_url}/foods/log/date/{date}.json', headers)
        if response.status_code == 200:
            food_log = response.json()
            nutrition_summary = food_log.get('summary', {})
            data['calories_in'] = nutrition_summary.get('calories', 0)
            data['carbs'] = nutrition_summary.get('carbs', 0)
            data['fat_intake'] = nutrition_summary.get('fat', 0)
            data['protein'] = nutrition_summary.get('protein', 0)
            data['fiber'] = nutrition_summary.get('fiber', 0)
            data['sodium'] = nutrition_summary.get('sodium', 0)

        return data

    except requests.exceptions.RequestException as e:
        print(f"  Error fetching Fitbit data: {e}")
        return None


def update_notion_database(date, fitbit_data, food_data=None):
    """Update or create entry in Notion database"""
    load_dotenv()

    notion = Client(auth=os.getenv('NOTION_TOKEN'))
    database_id = os.getenv('NOTION_DATABASE_ID')

    # Check if entry already exists for this date
    existing_pages = notion.databases.query(
        database_id=database_id,
        filter={
            "property": "日付",
            "date": {
                "equals": date
            }
        }
    )

    # Format date as Japanese style for display name
    date_obj = datetime.strptime(date, '%Y-%m-%d')
    date_display = f"{date_obj.year}年{date_obj.month:02d}月{date_obj.day:02d}日"

    # Prepare properties with all Fitbit metrics
    properties = {
        "名前": {"title": [{"text": {"content": date_display}}]},
        "日付": {"date": {"start": date}},
        "歩数": {"number": fitbit_data.get('steps', 0)},
        "距離 (km)": {"number": round(fitbit_data.get('distance', 0), 2)},
        "消費カロリー (kcal)": {"number": fitbit_data.get('calories', 0)},
        "アクティブ時間 (分)": {"number": fitbit_data.get('active_minutes', 0)},
        "睡眠時間 (時間)": {"number": fitbit_data.get('sleep_hours', 0)},
        "睡眠効率 (%)": {"number": fitbit_data.get('sleep_efficiency', 0)},
        "深い睡眠 (分)": {"number": fitbit_data.get('deep_sleep', 0)},
        "浅い睡眠 (分)": {"number": fitbit_data.get('light_sleep', 0)},
        "レム睡眠 (分)": {"number": fitbit_data.get('rem_sleep', 0)},
        "脂肪燃焼ゾーン (分)": {"number": fitbit_data.get('fat_burn_minutes', 0)},
        "有酸素ゾーン (分)": {"number": fitbit_data.get('cardio_minutes', 0)},
        "ピークゾーン (分)": {"number": fitbit_data.get('peak_minutes', 0)},
    }

    # Add optional properties if available
    if fitbit_data.get('resting_heart_rate'):
        properties["安静時心拍数 (bpm)"] = {
            "number": fitbit_data['resting_heart_rate']}

    if fitbit_data.get('sleep_start'):
        time_part = fitbit_data['sleep_start'].split('T')[1].split(':')
        properties["就寝時刻"] = {"rich_text": [
            {"text": {"content": f"{time_part[0]}:{time_part[1]}"}}]}

    if fitbit_data.get('sleep_end'):
        time_part = fitbit_data['sleep_end'].split('T')[1].split(':')
        properties["起床時刻"] = {"rich_text": [
            {"text": {"content": f"{time_part[0]}:{time_part[1]}"}}]}

    if fitbit_data.get('weight'):
        properties["体重 (kg)"] = {"number": fitbit_data['weight']}

    if fitbit_data.get('bmi'):
        properties["BMI"] = {"number": fitbit_data['bmi']}

    if fitbit_data.get('body_fat'):
        properties["体脂肪率 (%)"] = {"number": fitbit_data['body_fat']}

    if fitbit_data.get('hrv_daily_rmssd'):
        properties["HRV 日次 (ms)"] = {"number": fitbit_data['hrv_daily_rmssd']}

    if fitbit_data.get('hrv_deep_rmssd'):
        properties["HRV 深睡眠 (ms)"] = {"number": fitbit_data['hrv_deep_rmssd']}

    # Nutrition data (from Fitbit app food logging)
    if fitbit_data.get('calories_in'):
        properties["摂取カロリー (kcal)"] = {"number": fitbit_data['calories_in']}

    if fitbit_data.get('carbs'):
        properties["炭水化物 (g)"] = {"number": fitbit_data['carbs']}

    if fitbit_data.get('fat_intake'):
        properties["脂質 (g)"] = {"number": fitbit_data['fat_intake']}

    if fitbit_data.get('protein'):
        properties["たんぱく質 (g)"] = {"number": fitbit_data['protein']}

    if fitbit_data.get('fiber'):
        properties["食物繊維 (g)"] = {"number": fitbit_data['fiber']}

    if fitbit_data.get('sodium'):
        properties["ナトリウム (g)"] = {"number": fitbit_data['sodium']}

    try:
        if existing_pages['results']:
            # Update existing page
            page_id = existing_pages['results'][0]['id']
            notion.pages.update(page_id=page_id, properties=properties)
            print(f"  Updated existing entry for {date}")
        else:
            # Create new page
            notion.pages.create(
                parent={"database_id": database_id},
                properties=properties
            )
            print(f"  Created new entry for {date}")

    except Exception as e:
        print(f"  Error updating Notion: {e}")


def main():
    """Main sync function"""
    print("Starting Fitbit to Notion sync...")

    # Sync both today and yesterday
    today = datetime.now().strftime('%Y-%m-%d')
    yesterday = get_yesterday_date()

    for date in [yesterday, today]:
        print(f"Syncing data for: {date}")

        fitbit_data = get_fitbit_data(date)
        if not fitbit_data:
            print(f"  Failed to fetch Fitbit data for {date}")
            continue

        print("  Fitbit data fetched:")
        for key, value in fitbit_data.items():
            if value is not None and value != 0:
                print(f"    {key}: {value}")

        update_notion_database(date, fitbit_data)

    print("Sync completed!")


if __name__ == "__main__":
    main()
