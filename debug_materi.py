import cloudscraper
import os
from bs4 import BeautifulSoup
import re
import json
from dotenv import load_dotenv

load_dotenv()
scraper = cloudscraper.create_scraper()
nim = os.getenv("ECLASS_TEST_ID") or input("Enter your NIM: ")
password = os.getenv("ECLASS_TEST_PASSWORD") or input("Enter your Password: ")

# Login with the correct URL
LOGIN_URL = "https://eclass.ukdw.ac.id/id/home/do_login"
resp = scraper.post(LOGIN_URL, data={'id': nim, 'password': password})
print('Login status:', resp.status_code)
cookies = dict(scraper.cookies)
print('Cookies:', cookies)

# Get kelas
KELAS_URL = "https://eclass.ukdw.ac.id/e-class/id/kelas/index"
resp2 = scraper.post(KELAS_URL)
soup2 = BeautifulSoup(resp2.text, 'html.parser')

class_ids = []
for a in soup2.find_all('a', href=True):
    href = a['href']
    match = re.search(r'/kelas/detail/([A-Za-z0-9]+)', href)
    if match:
        class_ids.append(match.group(1))
class_ids = list(set(class_ids))
print(f'Classes: {class_ids}')

# Test calling local FastAPI API for materi
import requests
cookie_val = cookies.get('ukdw_session', '')
print(f'\nTesting local FastAPI API with cookie: {cookie_val}')

for cid in class_ids:
    print(f'\n=== Testing /api/v1/materi/{cid} ===')
    try:
        r = requests.post(f'http://127.0.0.1:8000/api/v1/materi/{cid}', 
                         json={'cookies': cookies}, timeout=30)
        print(f'Status: {r.status_code}')
        data = r.json()
        print(f'Response: {json.dumps(data, indent=2)}')
        
        # Try downloading each item
        if data.get('success') and data.get('data'):
            for item in data['data']:
                link = item['link']
                title = item['title']
                is_dl = item.get('is_download', False)
                print(f'\n  Item: {title}')
                print(f'  Link: {link}')
                print(f'  Is Download: {is_dl}')
                
                if is_dl:
                    print(f'  Attempting download...')
                    dl_resp = scraper.get(link, cookies={'ukdw_session': cookie_val})
                    print(f'  Download status: {dl_resp.status_code}')
                    print(f'  Content-Type: {dl_resp.headers.get("content-type")}')
                    print(f'  Content-Disposition: {dl_resp.headers.get("content-disposition")}')
                    print(f'  Size: {len(dl_resp.content)} bytes')
                    # Check if it's actually HTML (login redirect)
                    ct = dl_resp.headers.get('content-type', '')
                    if 'text/html' in ct:
                        print(f'  WARNING: Got HTML instead of file!')
                        print(f'  First 200 chars: {dl_resp.text[:200]}')
    except Exception as e:
        print(f'Error: {e}')
