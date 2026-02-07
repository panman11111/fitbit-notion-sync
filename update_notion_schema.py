#!/usr/bin/env python3
"""
Update Notion database schema to include food tracking columns
Run this once to add the necessary columns for food photo integration
"""

import os
from notion_client import Client
from dotenv import load_dotenv

def update_database_schema():
    """Add food tracking columns to the Notion database"""
    load_dotenv()
    
    notion = Client(auth=os.getenv('NOTION_TOKEN'))
    database_id = os.getenv('NOTION_DATABASE_ID')
    
    if not database_id:
        print("❌ NOTION_DATABASE_ID not found in .env file")
        return
    
    print("🔄 Updating Notion database schema...")
    
    # New properties for food tracking
    new_properties = {
        "朝食": {
            "type": "rich_text",
            "rich_text": {}
        },
        "昼食": {
            "type": "rich_text",
            "rich_text": {}
        },
        "夕食": {
            "type": "rich_text",
            "rich_text": {}
        },
        "食事写真処理済み": {
            "type": "checkbox",
            "checkbox": {}
        }
    }
    
    try:
        # Get current database properties
        database = notion.databases.retrieve(database_id=database_id)
        existing_properties = database.get('properties', {})
        
        # Check which properties need to be added
        properties_to_add = {}
        for prop_name, prop_config in new_properties.items():
            if prop_name not in existing_properties:
                properties_to_add[prop_name] = prop_config
                print(f"  ➕ Adding column: {prop_name}")
            else:
                print(f"  ✅ Column already exists: {prop_name}")
        
        # Update database if there are new properties to add
        if properties_to_add:
            notion.databases.update(
                database_id=database_id,
                properties=properties_to_add
            )
            print(f"✅ Successfully added {len(properties_to_add)} new columns")
        else:
            print("✅ All required columns already exist")
            
    except Exception as e:
        print(f"❌ Error updating database schema: {e}")
        print("Make sure your Notion token has edit permissions for the database")

if __name__ == "__main__":
    update_database_schema()