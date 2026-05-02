import requests
import os
from dotenv import load_dotenv

load_dotenv()

url = os.getenv("PMB_API_URL", "http://127.0.0.1:8000/pmb.ukdw.ac.id/admisi")

# credentials
payload = {
    "uname": os.getenv("PMB_TEST_USERNAME") or input("Enter username: "),
    "pword": os.getenv("PMB_TEST_PASSWORD") or input("Enter password: ")
}

try:
    response = requests.post(url, json=payload)

    print(f"Status Code: {response.status_code}")
    print("Response Body:")
    print(response.json())
    
    

except Exception as e:
    print(f"Error: {e}")