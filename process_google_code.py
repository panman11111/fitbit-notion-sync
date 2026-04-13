#!/usr/bin/env python3
"""
Process Google OAuth authorization code to get tokens
"""

import os
import requests
from dotenv import load_dotenv

def process_auth_code():
    """Process the authorization code to get Google tokens"""
    load_dotenv()
    
    client_id = os.getenv('GOOGLE_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
    
    # Authorization code from the redirect URL
    auth_code = "4/0AVMBsJj0ephjl67daO38ULDyARJoM3A73rVkJzyc_7avp7_HP13gXoFIxJJL-PXR8vF8vQ"
    
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
            with open('.env', 'r') as f:
                content = f.read()
            
            # Update existing tokens
            lines = content.split('\n')

            for i, line in enumerate(lines):
                if line.startswith('GOOGLE_ACCESS_TOKEN='):
                    lines[i] = f'GOOGLE_ACCESS_TOKEN={access_token}'
                elif line.startswith('GOOGLE_REFRESH_TOKEN='):
                    lines[i] = f'GOOGLE_REFRESH_TOKEN={refresh_token}'
            
            # Add refresh token if not found
            if 'GOOGLE_REFRESH_TOKEN=' not in content:
                lines.append(f'GOOGLE_REFRESH_TOKEN={refresh_token}')
            
            content = '\n'.join(lines)
            
            with open('.env', 'w') as f:
                f.write(content)
            
            print()
            print("🔑 TOKENS UPDATED IN .env FILE")
            print()
            print("📋 UPDATE THESE GITHUB SECRETS:")
            print(f"GOOGLE_ACCESS_TOKEN={access_token}")
            print(f"GOOGLE_REFRESH_TOKEN={refresh_token}")
            print()
            print("Go to: https://github.com/radusqrt/fitbit-notion-sync/settings/secrets/actions")
            print("Update the GOOGLE_ACCESS_TOKEN and GOOGLE_REFRESH_TOKEN secrets")
            
        else:
            print("⚠️ No refresh token received")
            
        return True
    else:
        print(f"❌ Failed to get tokens: {response.text}")
        return False

if __name__ == "__main__":
    process_auth_code()