"""
Diagnostic script to verify MongoDB connection.

Usage:
    python scripts/check_connection.py
"""

import os
import sys
from pathlib import Path

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

# Load config from secrets.toml
try:
    import tomllib
except ImportError:
    import tomli as tomllib

secrets_path = Path(__file__).parent.parent / ".streamlit" / "secrets.toml"
if not secrets_path.exists():
    print(f"❌ secrets.toml not found at: {secrets_path}")
    sys.exit(1)

with open(secrets_path, "rb") as f:
    config = tomllib.load(f)

MONGO_URI = config.get("MONGO_URI")
MONGO_DB = config.get("MONGO_DB", "examadmin")

if not MONGO_URI:
    print("❌ MONGO_URI not set in secrets.toml")
    sys.exit(1)


def check_connection():
    """Verify MongoDB connection and print diagnostics."""
    
    print("=" * 70)
    print("🔍 MongoDB Connection Diagnostic")
    print("=" * 70)
    
    # Mask password in URI for display
    display_uri = MONGO_URI
    if "@" in MONGO_URI and "://" in MONGO_URI:
        scheme, rest = MONGO_URI.split("://", 1)
        if "@" in rest:
            creds, host = rest.split("@", 1)
            if ":" in creds:
                user, _ = creds.split(":", 1)
                display_uri = f"{scheme}://{user}:****@{host}"
    
    print(f"\n📌 Connection String:")
    print(f"   {display_uri}")
    print(f"\n📌 Database: {MONGO_DB}")
    
    # Attempt connection
    print(f"\n{'─' * 70}")
    print("🔌 Attempting connection...")
    print(f"{'─' * 70}")
    
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=10000)
        
        # 1. Test server info
        info = client.server_info()
        version = info.get("version")
        print(f"✅ Connected successfully!")
        print(f"\n📡 Server Version: {version}")
        
        # 2. Detect Atlas vs Local
        if "mongodb+srv://" in MONGO_URI or "mongodb.net" in MONGO_URI:
            print(f"\n🌐 Host Type: MongoDB Atlas (Cloud)")
        else:
            print(f"\n💻 Host Type: Local MongoDB")
        
        # 3. Show address
        try:
            addr = client.address
            print(f"📡 Server Address: {addr[0]}:{addr[1]}")
        except Exception:
            print(f"📡 Server Address: (SRV — resolved by driver)")
        
        # 4. List databases
        print(f"\n{'─' * 70}")
        print("🗄️  Available Databases:")
        print(f"{'─' * 70}")
        for db_name in client.list_database_names():
            print(f"   • {db_name}")
        
        # 5. Check target database
        print(f"\n{'─' * 70}")
        print(f"🎯 Target Database: {MONGO_DB}")
        print(f"{'─' * 70}")
        
        db = client[MONGO_DB]
        collections = db.list_collection_names()
        
        if not collections:
            print(f"   ⚠️  Database exists but has no collections")
        else:
            print(f"   ✅ Collections ({len(collections)}):")
            for coll in sorted(collections):
                count = db[coll].count_documents({})
                print(f"      • {coll:<25} {count:>5} documents")
        
        # 6. Check admin user
        print(f"\n{'─' * 70}")
        print("👤 Admin User Check:")
        print(f"{'─' * 70}")
        
        admin = db.users.find_one({"role": "admin"})
        if admin:
            print(f"   ✅ Admin user exists:")
            print(f"      Username: {admin.get('username')}")
            print(f"      Email:    {admin.get('email')}")
            print(f"      Role:     {admin.get('role')}")
        else:
            print(f"   ⚠️  No admin user found!")
            print(f"      Run: python scripts/bootstrap_admin.py")
        
        # 7. Summary
        print(f"\n{'=' * 70}")
        print("✅ DIAGNOSTIC COMPLETE")
        print(f"{'=' * 70}")
        print(f"\n   Status:      Connected")
        print(f"   Database:    {MONGO_DB}")
        print(f"   Collections: {len(collections)}")
        print(f"   Admin:       {'✅ Yes' if admin else '❌ No'}")
        print(f"\n{'=' * 70}\n")
        
        client.close()
        return True
        
    except ConnectionFailure as e:
        print(f"\n❌ CONNECTION FAILED")
        print(f"   Error: {e}")
        print(f"\n💡 Troubleshooting:")
        print(f"   1. Check your internet connection")
        print(f"   2. Verify MONGO_URI in secrets.toml")
        print(f"   3. Add your IP to Atlas Network Access:")
        print(f"      https://cloud.mongodb.com → Network Access")
        print(f"   4. Verify Atlas database user credentials")
        print(f"   5. Check if Atlas cluster is running")
        return False
        
    except OperationFailure as e:
        print(f"\n❌ AUTHENTICATION FAILED")
        print(f"   Error: {e}")
        print(f"\n💡 Fix:")
        print(f"   1. Verify username/password in MONGO_URI")
        print(f"   2. Check Database Access in Atlas")
        print(f"   3. Verify user has 'readWrite' on '{MONGO_DB}'")
        return False
        
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR")
        print(f"   Type: {type(e).__name__}")
        print(f"   Error: {e}")
        return False


if __name__ == "__main__":
    success = check_connection()
    sys.exit(0 if success else 1)