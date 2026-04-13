#!/usr/bin/env python3
"""
Process Google OAuth authorization code to get tokens
"""

import os
import pathlib
import requests
from dotenv import load_dotenv

_ENV_PATH = pathlib.Path(__file__).parent / ".env"

def process_auth_code():
    """Process the authorization code to get Google tokens"""
    load_dotenv()
    
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    
    # Authorization code from the redirect URL
    auth_code = input("Paste the authorization code from the redirect URL: ").strip()
    if not auth_code:
        print("No authorization code provided")
        return False

    print(f"🔄 Processing authorization code: {auth_code[:20]}...")
    
    # Exchange code for tokens
    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'code': auth_code,
        'grant_type': 'authorization_code',
        'redirect_uri': 'http://localhost:8080'
    }
    
    print("🔄 Exchanging code for tokens...")
    response = requests.post(token_url, data=token_data)
    
    if response.status_code == 200:
        tokens = response.json()
        access_token = tokens['access_token']
        refresh_token = tokens.get('refresh_token', '')
        
        print("✅ Google OAuth successful!")
        print(f"📋 Access token: {access_token[:20]}...")
        if refresh_token:
            print(f"📋 Refresh token: {refresh_token[:20]}...")
            
            # Update .env file
            if _ENV_PATH.exists():
                content = _ENV_PATH.read_text(encoding="utf-8")
            else:
                content = ""

            lines = content.split('\n')
            for i, line in enumerate(lines):
                if line.startswith('GOOGLE_ACCESS_TOKEN='):
                    lines[i] = f'GOOGLE_ACCESS_TOKEN={access_token}'
                elif line.startswith('GOOGLE_REFRESH_TOKEN='):
                    lines[i] = f'GOOGLE_REFRESH_TOKEN={refresh_token}'

            if 'GOOGLE_REFRESH_TOKEN=' not in content:
                lines.append(f'GOOGLE_REFRESH_TOKEN={refresh_token}')

            _ENV_PATH.write_text('\n'.join(lines), encoding="utf-8")

            print()
            print("🔑 TOKENS UPDATED IN .env FILE")
            print("   .env ファイルを参照して GOOGLE_ACCESS_TOKEN / GOOGLE_REFRESH_TOKEN を")
            print("   GitHub Secrets に登録してください。")
            
        else:
            print("⚠️ No refresh token received")
            
        return True
    else:
        print(f"❌ Failed to get tokens: {response.text}")
        return False

if __name__ == "__main__":
    process_auth_code()