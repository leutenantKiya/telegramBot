import cloudscraper

url = "https://eclass.ukdw.ac.id/e-class/id/download/materi/103352/Pancasila_Makna_dan_Kesehariannya.pdf"

# Cookie dari intercept jaringan (browser) harus disertakan
# Tanpa cookie, server akan redirect ke halaman login
cookies = {
    "ukdw_session": "ra2c54v9rmct5l4ceubvtjgit1sc8ggj",
    "cf_clearance": "m10Rv2wJADCWY4t4C4ZkbqPI5Xi.tO8yYXcMGvg_H.o-1777639801-1.2.1.1-1KQGMoNrtU4NYlozg21Ozsk6e93b7hEgUPKRXbdLtsw4OZCo24pPym2ztAMql2ETtKcgxOgK5WP45XbtNUlnM8cTF8d20WZLO0LmxNt2MWuUELn4i2.J.3CgL5w1f4m.KE_XD6G_fhCH0Zkg9CzmTKhKtxV9bml42xFs6zlPJNz0cDixwDR1KHpvauuGbugcTcA4XoeZcxAv798NdP4aiSyuLICYcwB2ytNF6E_UO4rcFcgv9PGAK3dDI.ylRjOhZf6T_3tBajru0rBpIzl2aTMy2KqLco85b1xYqJVKk8SynV9RzujtQX_VmNtHGT5S9xI13wz0WbjkivJtGIH1ldmXevGiWWy9yEEWRxnN.hSH8dfQQRq550Ly8WVopw8LCHmRX2PR45fxzVy.n4D47HDS5SsNa9kQfL_1gzWIJWI"
}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://eclass.ukdw.ac.id/e-class/id/materi/index/MH1073",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Upgrade-Insecure-Requests": "1",
}

# Pakai cloudscraper supaya bisa bypass Cloudflare challenge
session = cloudscraper.create_scraper()
session.cookies.update(cookies)

response = session.get(url, headers=headers, allow_redirects=True, timeout=120)

print(f"Status: {response.status_code}")
print(f"Content-Type: {response.headers.get('content-type', 'unknown')}")
print(f"Content-Length: {len(response.content)} bytes")

# Cek apakah response-nya HTML (berarti redirect ke login) atau file asli
content_prefix = response.content[:100].lstrip().lower()
is_html = content_prefix.startswith(b"<!doctype html") or content_prefix.startswith(b"<html")

if response.status_code == 200 and not is_html:
    with open("downloaded.pdf", "wb") as f:
        f.write(response.content)
    print("[OK] Download berhasil!")
else:
    print("[GAGAL] Download gagal - server mengembalikan HTML (kemungkinan halaman login)")
    print(f"Preview: {response.text[:300]}")