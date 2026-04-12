#!/usr/bin/env python3
"""
Fitbit OAuth Setup - Fresh authentication flow
"""

import os
import webbrowser
from urllib.parse import urlparse, parse_qs
import requests
import base64
from dotenv import load_dotenv
from token_store import persist_tokens

def setup_fitbit_oauth():
    """Set up fresh Fitbit OAuth tokens"""
    load_dotenv()

    client_id = os.getenv('FITBIT_CLIENT_ID')
    client_secret = os.getenv('FITBIT_CLIENT_SECRET')

    if not all([client_id, client_secret]):
        print("Missing Fitbit credentials in .env file")
        print("Add these to your .env file from your Fitbit app:")
        print("FITBIT_CLIENT_ID=your_client_id")
        print("FITBIT_CLIENT_SECRET=your_client_secret")
        return False

    # OAuth authorization URL
    scopes = "activity%20heartrate%20location%20nutrition%20profile%20settings%20sleep%20social%20weight"
    auth_url = f"https://www.fitbit.com/oauth2/authorize?response_type=code&client_id={client_id}&scope={scopes}&expires_in=86400"

    print("Setting up fresh Fitbit OAuth...")
    print("1. Opening browser for Fitbit authorization...")
    webbrowser.open(auth_url)

    print("2. After authorization, you'll be redirected to a URL like:")
    print("   http://localhost:8080/?code=XXXXXXX&state=XXXXXXX")
    print("3. Copy that full URL and paste it here:")

    callback_url = input("Paste the callback URL here: ")

    # Extract code from URL
    try:
        parsed_url = urlparse(callback_url)
        code = parse_qs(parsed_url.query).get('code', [None])[0]

        if not code:
            print("No authorization code found in URL")
            return False

        print(f"Found authorization code: {code[:10]}...")

    except Exception as e:
        print(f"Error parsing URL: {e}")
        return False

    # Exchange code for tokens
    token_url = "https://api.fitbit.com/oauth2/token"

    # Create Basic Auth header
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {encoded_credentials}'
    }

    data = {
        'client_id': client_id,
        'grant_type': 'authorization_code',
        'code': code
    }

    try:
        print("Exchanging code for tokens...")
        response = requests.post(token_url, headers=headers, data=data)
    except Exception as e:
        print(f"Error getting tokens: {e}")
        return False

    if response.status_code != 200:
        print(f"Failed to get tokens: {response.status_code}")
        print(f"   Response: {response.text}")
        return False

    tokens = response.json()
    print("Successfully obtained Fitbit tokens!")
    print(f"   Access token: {tokens['access_token'][:20]}...")
    print(f"   Refresh token: {tokens['refresh_token'][:20]}...")
    print(f"   Expires in: {tokens['expires_in']} seconds")

    try:
        persist_tokens(tokens["access_token"], tokens["refresh_token"])
    except RuntimeError as e:
        print(f"トークン保存に失敗しました: {e}")
        return False

    print()
    print("Fitbit OAuth setup complete!")
    return True

if __name__ == "__main__":
    print("Fitbit OAuth Setup")
    print("=" * 30)

    success = setup_fitbit_oauth()

    if success:
        print()
        print("NEXT STEPS:")
        print("1. Run the manual sync again")
        print()

        # Show Google secrets guidance (values are NOT printed for security)
        load_dotenv()
        google_access = os.getenv('GOOGLE_ACCESS_TOKEN')

        if google_access:
            print("GOOGLE SECRETS (also needed):")
            print("  - Refer to your .env file for GOOGLE_ACCESS_TOKEN, GOOGLE_REFRESH_TOKEN, and GOOGLE_API_KEY")
            print("  - Add these to GitHub Secrets manually if needed")
    else:
        print()
        print("Setup failed. Please check the errors above and try again.")
