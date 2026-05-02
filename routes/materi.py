import re
from typing import Any, Dict, Optional

from config import Config
from bs4 import BeautifulSoup as bs
from utils.response import Response
from fastapi import APIRouter, Body

materi_bp = APIRouter()

@materi_bp.post('/{id}')
def get_materi(id: str, data: Optional[Dict[str, Any]] = Body(default=None)):
  try:
    data = data or {}
    session = Config.create_session()

    if not id:
      return Response.Error("Kelas ID is required")
    if not data.get('cookies'):
      return Response.Error('Cookies are required')

    cookies = data.get('cookies')
    if isinstance(cookies, str):
      cookies = {'ukdw_session': cookies}
    elif isinstance(cookies, dict) and 'ukdw_session' not in cookies:
        cookies = {'ukdw_session': cookies.get('ukdw_session', cookies)}

    response = session.post(Config.MATERI_URL + f"/{id}", cookies=cookies)
    
    if response.ok:
      soup = bs(response.text, 'html.parser')
      if soup.find('div', id='login-box-content'):
        return Response.Error("Sesi login e-class sampun kadaluarsa. Monggo /login malih.")
      materi_list = []
      
      # Parse table rows - the structure is:
      # Row: [No, Judul, Jenis File, Grup, (optional empty), Aktivitas]
      # Links are inside the row as <a> tags
      rows = soup.find_all('tr')
      for row in rows:
        cells = row.find_all('td')
        if len(cells) < 3:
            continue
            
        # Find links in this row
        link_tags = []
        for candidate in row.find_all('a', href=True):
            candidate_href = candidate.get('href', '')
            if candidate_href == '#' or 'javascript' in candidate_href or 'cdn-cgi' in candidate_href:
                continue
            # Skip "Tambah Materi" link
            if 'tambah_materi' in candidate_href:
                continue
            # Skip nav links like Kelas, Tugas, Feedback, etc.
            if any(nav in candidate_href for nav in ['/kelas/index', '/kelas/detail/', '/kelas/pengumuman/', 
                   '/kelas/tugas/', '/kelas/peserta/', '/kelas/asisten/', '/kelas/nilai/', '/kelas/presensi/']):
                continue
            link_tags.append(candidate)

        if not link_tags:
            continue

        download_tag = next(
            (
                candidate for candidate in link_tags
                if 'download' in candidate.get_text(" ", strip=True).lower()
                or '/download/' in candidate.get('href', '').lower()
            ),
            None
        )
        link_tag = download_tag or link_tags[0]
        href = link_tag['href']
        link_text = link_tag.get_text(strip=True)
            
        # Get title from the second cell (index 1)
        title = cells[1].get_text(strip=True) if len(cells) > 1 else "Materi"
        # Clean up the title - remove "oleh: ..." suffix
        title = re.sub(r'oleh:\s+.*$', '', title).strip()
        
        # Get file type from third cell
        file_type = cells[2].get_text(strip=True) if len(cells) > 2 else ""
        # Clean up file type (e.g. "PDF497.1 KB" -> "PDF")
        file_type_clean = re.match(r'^([A-Z]+)', file_type)
        file_type_clean = file_type_clean.group(1) if file_type_clean else file_type
        
        # Determine if it's a downloadable file or an external/view link
        # Items with type "URL" or link text "Lihat" are not downloadable files
        if file_type_clean.upper() == 'URL':
            is_download = False
        elif download_tag:
            is_download = True
        else:
            is_download = 'download' in link_text.lower() or '/download/' in href.lower()
        
        materi_list.append({
            "title": title,
            "link": href,
            "alt_links": [candidate.get('href') for candidate in link_tags if candidate.get('href') != href],
            "referer": Config.MATERI_URL + f"/{id}",
            "type": file_type_clean,
            "is_download": is_download
        })
               
      return Response.Ok(materi_list)

    return Response.Error("Failed to fetch materi")
  except Exception as e:
    return Response.Error(str(e))
