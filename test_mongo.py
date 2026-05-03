import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
uri = os.getenv("MONGO_URI")

if not uri:
    print("[FAIL] MONGO_URI not found in .env")
    exit(1)

print("[INFO] Connecting to MongoDB Atlas...")

try:
    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
        socketTimeoutMS=20000,
        tls=True,
        tlsAllowInvalidCertificates=False
    )
    client.admin.command('ping')
    print("[OK] Connected to MongoDB Atlas!")

    print("[INFO] Creating test_db.test_col...")
    test_db = client['test_db']
    test_col = test_db['test_col']

    result = test_col.insert_one({"message": "Hello from Aily Bot!", "status": "success"})
    print(f"[OK] Inserted document ID: {result.inserted_id}")

    doc = test_col.find_one({"_id": result.inserted_id})
    print(f"[OK] Read back: {doc}")

    client.drop_database('test_db')
    print("[OK] Cleanup done (test_db dropped)")

    print("\n[PASS] ALL MONGODB ATLAS TESTS PASSED!")

except Exception as e:
    print(f"\n[FAIL] MongoDB Atlas error: {e}")
