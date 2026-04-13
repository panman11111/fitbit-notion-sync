#!/usr/bin/env python3
"""
Google Drive Food Detection Integration
Retrieves food photos from Google Drive folder, extracts metadata, and classifies meals
"""

import os
import tempfile
from datetime import datetime
from typing import Dict, List, Optional
import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import google.generativeai as genai
from PIL import Image
from PIL.ExifTags import TAGS
from dotenv import load_dotenv

# Your Google Drive folder ID from the URL
DRIVE_FOLDER_ID = "1FJhSf-gauhVnMwcHwOez1omDQ7jJtp5B"

def refresh_google_credentials():
    """Refresh Google OAuth credentials if needed"""
    load_dotenv()
    
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    refresh_token = os.getenv('GOOGLE_REFRESH_TOKEN')
    access_token = os.getenv('GOOGLE_ACCESS_TOKEN')
    
    if not all([client_id, client_secret]):
        raise Exception("Missing Google OAuth credentials in .env file")
    
    # Create credentials object
    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri='https://oauth2.googleapis.com/token'
    )
    
    # Refresh if needed
    if not credentials.valid:
        print("🔄 Google credentials expired, refreshing...")
        credentials.refresh(Request())
        
        # Update .env file with new token
        with open('.env', 'r') as f:
            content = f.read()
        
        if 'GOOGLE_ACCESS_TOKEN=' in content:
            content = content.replace(
                f'GOOGLE_ACCESS_TOKEN={access_token}',
                f'GOOGLE_ACCESS_TOKEN={credentials.token}'
            )
        else:
            content += f'\nGOOGLE_ACCESS_TOKEN={credentials.token}\n'
        
        with open('.env', 'w') as f:
            f.write(content)
    
    return credentials

def get_drive_photos(date: str) -> List[Dict]:
    """Get photos from Google Drive folder for a specific date"""
    credentials = refresh_google_credentials()
    service = build('drive', 'v3', credentials=credentials)
    
    # Parse target date
    target_date = datetime.strptime(date, '%Y-%m-%d')
    
    try:
        # Query files in the folder
        query = f"'{DRIVE_FOLDER_ID}' in parents and mimeType contains 'image/'"
        
        results = service.files().list(
            q=query,
            fields="files(id,name,createdTime,modifiedTime,imageMediaMetadata,webContentLink)",
            orderBy='createdTime desc'
        ).execute()
        
        files = results.get('files', [])
        print(f"📸 Found {len(files)} photos in Drive folder")
        
        # Filter by date and prepare file info
        photos = []
        for file in files:
            file_info = {
                'id': file['id'],
                'name': file['name'],
                'created_time': file.get('createdTime'),
                'modified_time': file.get('modifiedTime'),
                'image_metadata': file.get('imageMediaMetadata', {}),
                'download_url': f"https://drive.google.com/uc?id={file['id']}"
            }
            
            # Try to determine photo timestamp
            photo_time = get_photo_timestamp(file_info, credentials)
            if photo_time:
                photo_date = photo_time.date()
                if photo_date == target_date.date():
                    file_info['photo_time'] = photo_time
                    photos.append(file_info)
                    print(f"  📷 {file['name']} - {photo_time.strftime('%H:%M')}")
        
        print(f"📅 Found {len(photos)} photos for {date}")
        return photos
        
    except Exception as e:
        print(f"❌ Error retrieving Drive photos: {e}")
        return []

def get_photo_timestamp(file_info: Dict, credentials: Credentials) -> Optional[datetime]:
    """Extract the original photo timestamp (when picture was taken) from various sources"""
    
    # Priority 1: Google Drive's image metadata (includes original timestamp)
    image_meta = file_info.get('image_metadata', {})
    if 'time' in image_meta:
        try:
            original_time = datetime.fromisoformat(image_meta['time'].replace('Z', '+00:00'))
            print(f"  🕒 Original timestamp from Drive metadata: {original_time}")
            return original_time
        except Exception:
            pass

    # Priority 2: Download and extract EXIF data (most reliable for original timestamp)
    try:
        download_url = f"https://www.googleapis.com/drive/v3/files/{file_info['id']}?alt=media"
        headers = {'Authorization': f'Bearer {credentials.token}'}
        
        response = requests.get(download_url, headers=headers)
        if response.status_code == 200:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                temp_file.write(response.content)
                temp_path = temp_file.name
            
            try:
                exif_time = extract_exif_timestamp(temp_path)
                if exif_time:
                    print(f"  📸 Original timestamp from EXIF: {exif_time}")
                    os.unlink(temp_path)
                    return exif_time
                os.unlink(temp_path)
            except Exception:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
    except Exception as e:
        print(f"  ⚠️ Could not extract EXIF data: {e}")
    
    # Priority 3: Try Drive's imageMediaMetadata fields
    if 'width' in image_meta or 'height' in image_meta:
        # Sometimes Drive stores more metadata fields
        for field in ['date', 'datetime', 'dateTime']:
            if field in image_meta:
                try:
                    meta_time = datetime.fromisoformat(str(image_meta[field]).replace('Z', '+00:00'))
                    print(f"  📅 Timestamp from metadata field '{field}': {meta_time}")
                    return meta_time
                except Exception:
                    continue
    
    # Priority 4: Parse filename for timestamp (if user includes date/time in filename)
    filename = file_info.get('name', '')
    timestamp_from_name = parse_timestamp_from_filename(filename)
    if timestamp_from_name:
        print(f"  📝 Timestamp from filename: {timestamp_from_name}")
        return timestamp_from_name
    
    # Last resort: Use upload time (created_time) but warn user
    if file_info.get('created_time'):
        try:
            upload_time = datetime.fromisoformat(file_info['created_time'].replace('Z', '+00:00'))
            print(f"  ⚠️ Using upload time (not original photo time): {upload_time}")
            return upload_time
        except Exception:
            pass

    return None

def extract_exif_timestamp(image_path: str) -> Optional[datetime]:
    """Extract timestamp from image EXIF data"""
    try:
        image = Image.open(image_path)
        exif = image._getexif()
        
        if exif:
            for tag_id, value in exif.items():
                tag = TAGS.get(tag_id, tag_id)
                # Prioritize DateTimeOriginal (when photo was taken)
                if tag == 'DateTimeOriginal':
                    try:
                        return datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                    except Exception:
                        continue
                elif tag in ['DateTime', 'DateTimeDigitized']:
                    try:
                        return datetime.strptime(value, '%Y:%m:%d %H:%M:%S')
                    except Exception:
                        continue
    except Exception:
        pass
    
    return None

def parse_timestamp_from_filename(filename: str) -> Optional[datetime]:
    """Parse timestamp from filename patterns like IMG_20240723_142530.jpg"""
    import re
    
    # Common filename patterns with timestamps
    patterns = [
        r'(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})',  # 20240723_142530
        r'(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})',  # 2024-07-23_14-25-30
        r'(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})',  # 2024-07-23 14:25:30
        r'IMG_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})',  # IMG_20240723_142530
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            try:
                year, month, day, hour, minute, second = map(int, match.groups())
                return datetime(year, month, day, hour, minute, second)
            except Exception:
                continue
    
    return None

def classify_meal_time(photo_time: datetime) -> Optional[str]:
    """Classify photo time into breakfast, lunch, or dinner"""
    hour = photo_time.hour
    
    # Meal time classification (24-hour format)
    if 6 <= hour < 11:
        return 'breakfast'
    elif 11 <= hour < 16:
        return 'lunch'
    elif 17 <= hour < 23:
        return 'dinner'
    else:
        return None  # Outside typical meal times

def analyze_food_image(image_url: str) -> Optional[str]:
    """Analyze image using Gemini AI to detect and describe food"""
    load_dotenv()
    
    # Configure Gemini API
    api_key = os.getenv('GOOGLE_API_KEY')
    if not api_key:
        print("⚠️ GOOGLE_API_KEY not found in .env file")
        return None
    
    genai.configure(api_key=api_key)
    
    try:
        # Download image from Drive with proper authentication
        credentials = refresh_google_credentials()
        headers = {'Authorization': f'Bearer {credentials.token}'}
        
        response = requests.get(image_url, headers=headers)
        if response.status_code != 200:
            print(f"❌ Failed to download image: {response.status_code}")
            return None
        
        # Save image temporarily for processing
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            temp_file.write(response.content)
            temp_path = temp_file.name
        
        try:
            # Upload image to Gemini
            image_file = genai.upload_file(temp_path)
            
            # Initialize Gemini model
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            # Create prompt for food analysis
            prompt = """List only the food and drink items in this image. No descriptions, no presentation details, no extra words.

Good examples:
- "cappuccino" (not "coffee with latte art" or "cup of coffee")
- "fried eggs with tomatoes and cucumber" (not "plate of fried eggs served with fresh tomatoes and cucumber slices")
- "pizza" (not "slice of pizza on a white plate")
- "caesar salad" (not "fresh caesar salad with croutons")

Just the food items, separated by commas if multiple dishes.

If no food/drink is visible, respond "NO_FOOD"."""
            
            # Generate response
            result = model.generate_content([prompt, image_file])
            
            # Clean up temp file
            os.unlink(temp_path)
            
            # Process response
            if result.text.strip() == "NO_FOOD":
                return None
            
            return result.text.strip()
            
        except Exception as e:
            # Clean up temp file if error occurs
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise e
            
    except Exception as e:
        print(f"❌ Error analyzing image with Gemini: {e}")
        return None

def process_drive_food_photos(date: str) -> Dict[str, List[str]]:
    """Process all photos from Drive folder for a date and return food descriptions by meal"""
    photos = get_drive_photos(date)
    
    if not photos:
        return {'breakfast': [], 'lunch': [], 'dinner': []}
    
    meal_foods = {'breakfast': [], 'lunch': [], 'dinner': []}
    
    for photo in photos:
        # Get photo timestamp
        photo_time = photo.get('photo_time')
        if not photo_time:
            print(f"⚠️ No timestamp for {photo['name']}, skipping")
            continue
        
        # Classify meal time
        meal = classify_meal_time(photo_time)
        if not meal:
            print(f"⚠️ Photo taken outside meal times: {photo_time.strftime('%H:%M')}")
            continue
        
        # Get proper download URL for Gemini analysis
        file_id = photo['id']
        download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
        
        # Analyze image for food content
        food_description = analyze_food_image(download_url)
        
        if food_description:
            meal_foods[meal].append(food_description)
            print(f"🍽️ {meal.title()} ({photo_time.strftime('%H:%M')}): {food_description}")
        else:
            print(f"⚠️ No food detected in {photo['name']}")
    
    return meal_foods

def format_meal_text(food_items: List[str]) -> str:
    """Format list of food descriptions into readable text"""
    if not food_items:
        return ""
    
    if len(food_items) == 1:
        return food_items[0]
    
    # Combine multiple food descriptions
    return "; ".join(food_items)

if __name__ == "__main__":
    # Test the integration
    from datetime import datetime
    
    test_date = datetime.now().strftime('%Y-%m-%d')
    print(f"🧪 Testing Drive food photo processing for {test_date}")
    
    meal_data = process_drive_food_photos(test_date)
    
    for meal, foods in meal_data.items():
        if foods:
            print(f"{meal.title()}: {format_meal_text(foods)}")
        else:
            print(f"{meal.title()}: No food photos found")