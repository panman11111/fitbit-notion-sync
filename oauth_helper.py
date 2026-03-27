#!/usr/bin/env python3
"""
OAuth helper to refresh Fitbit and Google Drive tokens
"""

import os
import webbrowser
from urllib.parse import urlparse, parse_qs
import requests
from dotenv import load_dotenv

def refresh_fitbit_tokens():
    """Refresh Fitbit OAuth tokens"""
    load_dotenv()
    
    client_id = os.getenv('FITBIT_CLIENT_ID')
    client_secret = os.getenv('FITBIT_CLIENT_SECRET')
    refresh_token = os.getenv('FITBIT_REFRESH_TOKEN')
    
    if not all([client_id, client_secret, refresh_token]):
        print("❌ Missing Fitbit credentials in .env file")
        return False
    
    print("🔄 Refreshing Fitbit tokens...")
    
    # Refresh token request
    token_url = "https://api.fitbit.com/oauth2/token"
    import base64
    credentials = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {credentials}'
    }
    
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    
    try:
        response = requests.post(token_url, headers=headers, data=data)
        
        if response.status_code == 200:
            tokens = response.json()
            
            # Update .env file
            with open('.env', 'r') as f:
                content = f.read()
            
            # Replace tokens
            content = content.replace(
                f'FITBIT_ACCESS_TOKEN={os.getenv("FITBIT_ACCESS_TOKEN")}',
                f'FITBIT_ACCESS_TOKEN={tokens["access_token"]}'
            )
            content = content.replace(
                f'FITBIT_REFRESH_TOKEN={refresh_token}',
                f'FITBIT_REFRESH_TOKEN={tokens["refresh_token"]}'
            )
            
            with open('.env', 'w') as f:
                f.write(content)
            
            print("✅ Fitbit tokens refreshed successfully!")
            print(f"📋 New access token: {tokens['access_token'][:20]}...")
            print(f"📋 New refresh token: {tokens['refresh_token'][:20]}...")
            print()
            print("🔑 UPDATE GITHUB SECRETS:")
            print(f"FITBIT_ACCESS_TOKEN={tokens['access_token']}")
            print(f"FITBIT_REFRESH_TOKEN={tokens['refresh_token']}")
            
            return True
            
        else:
            print(f"❌ Failed to refresh Fitbit tokens: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error refreshing Fitbit tokens: {e}")
        return False

def setup_google_drive_oauth():
    """Set up Google Drive OAuth (first time)"""
    load_dotenv()
    
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    
    if not all([client_id, client_secret]):
        print("❌ Missing Google Client ID/Secret in .env file")
        print("Add these to your .env file:")
        print("GOOGLE_CLIENT_ID=your_client_id")
        print("GOOGLE_CLIENT_SECRET=your_client_secret")
        return False
    
    # OAuth flow
    auth_url = f"""https://accounts.google.com/o/oauth2/auth?client_id={client_id}&redirect_uri=http://localhost:8080&scope=https://www.googleapis.com/auth/drive.readonly&response_type=code&access_type=offline"""
    
    print("🔄 Setting up Google Drive OAuth...")
    print("1. Opening browser for Google authorization...")
    webbrowser.open(auth_url)
    
    print("2. After authorization, copy the full URL from your browser:")
    callback_url = input("Paste the callback URL here: ")
    
    # Extract code from URL
    parsed_url = urlparse(callback_url)
    code = parse_qs(parsed_url.query).get('code', [None])[0]
    
    if not code:
        print("❌ No authorization code found in URL")
        return False
    
    # Exchange code for tokens
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': 'http://localhost:8080'
    }
    
    try:
        response = requests.post(token_url, data=data)
        
        if response.status_code == 200:
            tokens = response.json()
            
            # Update .env file
            with open('.env', 'r') as f:
                content = f.read()
            
            # Add Google tokens
            if 'GOOGLE_ACCESS_TOKEN=' not in content:
                content += f'\nGOOGLE_ACCESS_TOKEN={tokens["access_token"]}\n'
            else:
                content = content.replace(
                    f'GOOGLE_ACCESS_TOKEN={os.getenv("GOOGLE_ACCESS_TOKEN", "")}',
                    f'GOOGLE_ACCESS_TOKEN={tokens["access_token"]}'
                )
            
            if 'GOOGLE_REFRESH_TOKEN=' not in content:
                content += f'GOOGLE_REFRESH_TOKEN={tokens.get("refresh_token", "")}\n'
            else:
                content = content.replace(
                    f'GOOGLE_REFRESH_TOKEN={os.getenv("GOOGLE_REFRESH_TOKEN", "")}',
                    f'GOOGLE_REFRESH_TOKEN={tokens.get("refresh_token", "")}'
                )
            
            with open('.env', 'w') as f:
                f.write(content)
            
            print("✅ Google Drive tokens obtained successfully!")
            print()
            print("🔑 ADD THESE GITHUB SECRETS:")
            print(f"GOOGLE_ACCESS_TOKEN={tokens['access_token']}")
            if tokens.get('refresh_token'):
                print(f"GOOGLE_REFRESH_TOKEN={tokens['refresh_token']}")
            
            return True
            
        else:
            print(f"❌ Failed to get Google tokens: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error getting Google tokens: {e}")
        return False

if __name__ == "__main__":
    print("🔧 OAuth Token Helper")
    print("=" * 30)
    
    # Check what needs to be done
    load_dotenv()
    
    fitbit_refresh = os.getenv('FITBIT_REFRESH_TOKEN')
    google_access = os.getenv('GOOGLE_ACCESS_TOKEN')
    
    if fitbit_refresh:
        print("🔄 Refreshing Fitbit tokens...")
        refresh_fitbit_tokens()
        print()
    
    if not google_access or not google_access.strip():
        print("🔄 Setting up Google Drive OAuth...")
        setup_google_drive_oauth()
    else:
        print("✅ Google tokens already exist")
        print("🔑 CURRENT GOOGLE SECRETS FOR GITHUB:")
        print(f"GOOGLE_ACCESS_TOKEN={google_access}")
        refresh_token = os.getenv('GOOGLE_REFRESH_TOKEN')
        if refresh_token:
            print(f"GOOGLE_REFRESH_TOKEN={refresh_token}")
    
    print()
    print("🎯 NEXT STEPS:")
    print("1. Copy the tokens above to GitHub Secrets")
    print("2. Go to: Settings → Secrets and variables → Actions")
    print("3. Update the secret values")
    print("4. Run the manual sync again")