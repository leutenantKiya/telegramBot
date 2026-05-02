from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv
from datetime import datetime
try:
    # for auto login protocol since i will have to store the pass and retrieve it back
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    Fernet = None
    InvalidToken = Exception

import os

load_dotenv()
USERNAME = os.getenv("DB_USERNAME")
PASSWORD = os.getenv("DB_PASSWORD")

# print(USERNAME, PASSWORD)
HOST = "localhost"
PORT = 27017

uri = f"mongodb://{USERNAME}:{PASSWORD}@{HOST}:{PORT}/?authSource=admin"
client = MongoClient(uri)
db_user = client['user']
user_collection = db_user['user_log']

class CredentialStorageError(Exception):
    pass

def _credential_cipher():
    if Fernet is None:
        raise CredentialStorageError("cryptography package is required to store e-class credentials")
    key = os.getenv("ECLASS_CREDENTIAL_KEY")
    if not key:
        raise CredentialStorageError("ECLASS_CREDENTIAL_KEY is not configured")
    try:
        return Fernet(key.encode())
    except Exception as e:
        raise CredentialStorageError("ECLASS_CREDENTIAL_KEY is invalid") from e

# function to save user
async def save_user(update, name=None):
    try:
        user = update.effective_user
        
        user_data = {
            "user_id" : str(user.id),
            "tele_username" : user.username,
            "first_name" : user.first_name,
            "last_name" : user.last_name
        }
        
        # if user already insert their prefered name
        if name:
            user_data["prefered_name"] = name
            
        user_collection.update_one(
            {"user_id": str(user.id)},
            {"$set": user_data}, 
            upsert=True
        )
        
    except ConnectionFailure:
        print("failed")

# function to get name 
def getName(user_id):
    try:
        data = user_collection.find_one({"user_id" : user_id})
        if data:
            return data.get("prefered_name", data.get("tele_username"))
        return None
    except:
        return "User ga ketemu"
    
# chat log
async def saveChatLog(user_id, message, role):
    try:
        log_entry = {
            "user_id": user_id,
            "role": role, 
            "message": message,
            "timestamp": datetime.now()
        }
        user_collection.update_one(
            {
                "user_id" : user_id
            },
            {
                "$push" : {"chat_logs" : log_entry}
            },
            upsert= True)
    except Exception as e:
        print(e)
        return None
    
def getLogHistory(user_id):
    try:
        log_data = user_collection.find({"user_id" : user_id})
    except Exception as e:
        print(e)

def validate_user(user_id):
    # check if user exist
    try:
        data = user_collection.find_one({"user_id": str(user_id)})
        return data is not None
    except Exception as e:
        print(f"validate_user error: {e}")
        return False

def save_eclass_credentials(user_id, nim, password):
    cipher = _credential_cipher()
    encrypted_password = cipher.encrypt(str(password).encode()).decode()
    user_collection.update_one(
        {"user_id": str(user_id)},
        {
            "$set": {
                "user_id": str(user_id),
                "eclass_credentials": {
                    "nim": str(nim),
                    "password": encrypted_password,
                    "updated_at": datetime.now()
                }
            }
        },
        upsert=True
    )
    return True

def get_eclass_credentials(user_id):
    data = user_collection.find_one(
        {"user_id": str(user_id)},
        {"eclass_credentials": 1}
    )
    credentials = data.get("eclass_credentials") if data else None
    if not credentials or not credentials.get("nim") or not credentials.get("password"):
        return None

    cipher = _credential_cipher()
    try:
        password = cipher.decrypt(credentials["password"].encode()).decode()
    except InvalidToken:
        return None

    return {
        "id": credentials["nim"],
        "password": password
    }

# def get_eclass_data(user_id):