import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_matakuliah():
    # Get COOKIES -> ukdw session
    print("=" * 50)
    print("Step 1: Testing Login")
    print("=" * 50)
    
    # NM AND PASS
    nim = input("Enter your NIM: ")
    password = input("Enter your Password: ")
    
    login_data = {
        "id": nim,
        "password": password
    }
    
    try:
        login_response = requests.post(f"{BASE_URL}/api/v1/login/", json=login_data)
        print(f"Login Status: {login_response.status_code}")
        print(f"Login Response: {json.dumps(login_response.json(), indent=2)}")
        
        if login_response.status_code == 200:
            login_json = login_response.json()
            if login_json.get('success'):
                cookies = login_json['data']['cookies']
                
                # GET matkul
                print("\n" + "=" * 50)
                print("Step 2: Getting Matakuliah List")
                print("=" * 50)
                
                matakuliah_data = {
                    "cookies": cookies
                }
                
                matakuliah_response = requests.post(
                    f"{BASE_URL}/api/v1/matakuliah/", 
                    json=matakuliah_data
                )
                print(f"Matakuliah Status: {matakuliah_response.status_code}")
                print(f"Matakuliah Response: {json.dumps(matakuliah_response.json(), indent=2)}")
                
                # Also test /all endpoint
                print("\n" + "=" * 50)
                print("Step 3: Testing /all Endpoint")
                print("=" * 50)
                
                matakuliah_all_response = requests.post(
                    f"{BASE_URL}/api/v1/matakuliah/all", 
                    json=matakuliah_data
                )
                print(f"Matakuliah /all Status: {matakuliah_all_response.status_code}")
                print(f"Matakuliah /all Response: {json.dumps(matakuliah_all_response.json(), indent=2)}")
            else:
                print(f"Login failed: {login_json.get('error')}")
        else:
            print("Login request failed")
            
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to server. Make sure the FastAPI app is running!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_matakuliah()
