#!/usr/bin/env python3
"""
Check Fitbit token expiration
"""

import os
import json
import base64
from datetime import datetime
from dotenv import load_dotenv

def decode_jwt_payload(token):
    """Decode JWT payload to check expiration"""
    try:
        # Split the JWT token
        parts = token.split('.')
        if len(parts) != 3:
            return None
        
        # Decode the payload (second part)
        payload = parts[1]
        # Add padding if needed
        payload += '=' * (4 - len(payload) % 4)
        
        # Decode base64
        decoded = base64.b64decode(payload)
        return json.loads(decoded)
    except Exception as e:
        print(f"Error decoding token: {e}")
        return None

def main():
    load_dotenv()
    
    access_token = os.getenv('FITBIT_ACCESS_TOKEN')
    if not access_token:
        print("❌ No Fitbit access token found")
        return
    
    payload = decode_jwt_payload(access_token)
    if not payload:
        print("❌ Could not decode token")
        return
    
    exp_timestamp = payload.get('exp')
    if exp_timestamp:
        exp_date = datetime.fromtimestamp(exp_timestamp)
        now = datetime.now()
        
        print("🔍 Fitbit token info:")
        print(f"  Expires: {exp_date}")
        print(f"  Current: {now}")
        print(f"  Status: {'⚠️ EXPIRED' if now > exp_date else '✅ Valid'}")
        
        if now > exp_date:
            print("\n🔄 Token has expired - need to refresh")
        else:
            time_left = exp_date - now
            print(f"  Time left: {time_left}")
    else:
        print("❌ No expiration found in token")

if __name__ == "__main__":
    main()