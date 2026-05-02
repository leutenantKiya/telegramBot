import re
from typing import Any, Dict, Optional

from config import Config
from bs4 import BeautifulSoup as bs
from utils.response import Response
from fastapi import APIRouter, Body

matakuliah_bp = APIRouter()

@matakuliah_bp.post('/')
def get_matakuliah(data: Optional[Dict[str, Any]] = Body(default=None)):
  try:
    data = data or {}
    session = Config.create_session()

    if not data.get('cookies'):
      return Response.Error('Cookies are required')

    cookies = data.get('cookies')
    
    # Try to get cookies as dict or as string
    if isinstance(cookies, str):
      cookies = {'ukdw_session': cookies}
    elif isinstance(cookies, dict):
      pass
    else:
      return Response.Error('Invalid cookies format')

    # Fetch the kelas page which contains the matakuliah list
    response = session.post(Config.KELAS_URL, cookies=cookies)
    
    if response.ok:
      soup = bs(response.text, 'html.parser')
      if soup.find('div', id='login-box-content'):
        return Response.Error("Sesi login e-class sampun kadaluarsa. Monggo /login malih.")
      
      # Find all kelas_box elements (each contains a matakuliah)
      kelas_boxes = soup.find_all('div', class_='kelas_box')
      matakuliah_list = []

      for kelas_box in kelas_boxes:
        h2_elements = kelas_box.find_all('h2')
        for h2_element in h2_elements:
          text = h2_element.text.strip()
          text = re.sub(r'\s{2,}', ' ', text)
          
          # Match pattern: [CODE] Matakuliah Name Class (SKS)
          match = re.match(r'\[(\w+)\]\s*(.*?)\s+([A-Z])\s*\((\d+)\s+SKS\)', text)
          if match:
            raw_text = kelas_box.get_text(separator="\n").strip()

            # Extract Ruang
            ruang_match = re.search(r'RUANG\s*:\s*([^\n]+)', raw_text)
            ruang = ruang_match.group(1).strip() if ruang_match else "N/A"

            # Extract Jadwal/Tanggal
            tanggal_matches = re.findall(r'[A-Z]+,\s+\d{2}:\d{2}\s+-\s+\d{2}:\d{2}\s+WIB', raw_text)
            tanggal_list = [t.strip() for t in tanggal_matches] if tanggal_matches else ["N/A"]

            # Extract Pengampu (lecturer)
            pengampu_start = raw_text.find("RUANG") + len("RUANG") if "RUANG" in raw_text else -1
            pengampu_text = raw_text[pengampu_start:].strip() if pengampu_start > 0 else raw_text

            pengampu_text = re.sub(r'^\s*:\s*[^\n]+\n?', '', pengampu_text)
            pengampu_text = re.sub(r'\s+', ' ', pengampu_text)
            pengampu_list = [p.strip() for p in pengampu_text.split('&')] if pengampu_text else ["N/A"]
            pengampu_list = [p for p in pengampu_list if p and len(p) < 100]  # Filter noise

            matakuliah_dict = {
              'id': match.group(1),
              'matkul': match.group(2).strip() + ' ' + match.group(3),
              'sks': match.group(4),
              'kelas': match.group(3),
              'ruang': ruang,
              'jadwal': tanggal_list,
              'pengampu': pengampu_list
            }

            matakuliah_list.append(matakuliah_dict)

      # If no matakuliah found in kelas_box, try alternative parsing
      if not matakuliah_list:
        # Try finding matakuliah from links or other elements
        matakuliah_links = soup.find_all('a', href=re.compile(r'/e-class/id/kelas/detail'))
        
        for link in matakuliah_links:
          href = link.get('href', '')
          text = link.get_text(strip=True)
          
          # Try to extract matakuliah info from link text or href
          matkul_match = re.search(r'\[(\w+)\]\s*(.+)', text)
          if matkul_match:
            matakuliah_list.append({
              'id': matkul_match.group(1),
              'matkul': matkul_match.group(2).strip(),
              'link': href
            })

      return Response.Ok({
        'count': len(matakuliah_list),
        'matakuliah': matakuliah_list
      })

    return Response.Error("Failed to fetch matakuliah list")
  except Exception as e:
    return Response.Error(str(e))

@matakuliah_bp.post('/all')
def get_all_matakuliah(data: Optional[Dict[str, Any]] = Body(default=None)):
  try:
    data = data or {}
    session = Config.create_session()

    if not data.get('cookies'):
      return Response.Error('Cookies are required')

    cookies = data.get('cookies')
    
    if isinstance(cookies, str):
      cookies = {'ukdw_session': cookies}

    # Try fetching main kelas page
    response = session.post(Config.KELAS_URL, cookies=cookies)
    
    if not response.ok:
      return Response.Error("Failed to access eclass")

    soup = bs(response.text, 'html.parser')
    if soup.find('div', id='login-box-content'):
      return Response.Error("Sesi login e-class sampun kadaluarsa. Monggo /login malih.")
    matakuliah_data = []

    # Method 1: Parse from kelas_box
    kelas_boxes = soup.find_all('div', class_='kelas_box')
    
    for kelas_box in kelas_boxes:
      matkul_info = {}
      
      # Get title from h2
      h2 = kelas_box.find('h2')
      if h2:
        title_text = h2.get_text(strip=True)
        title_match = re.match(r'\[(\w+)\]\s*(.+?)\s+([A-Z])\s*\((\d+)\s+SKS\)', title_text)
        if title_match:
          matkul_info['kode'] = title_match.group(1)
          matkul_info['nama'] = title_match.group(2).strip()
          matkul_info['kelas'] = title_match.group(3)
          matkul_info['sks'] = title_match.group(4)
      
      # Get details
      box_text = kelas_box.get_text(separator=' ', strip=True)
      
      # Extract ruang
      ruang = re.search(r'RUANG\s*:\s*(\S+)', box_text)
      if ruang:
        matkul_info['ruang'] = ruang.group(1)
      
      # Extract jadwal
      jadwal = re.findall(r'([A-Z]+,\s+\d{2}:\d{2}\s*-\s*\d{2}:\d{2}\s*WIB)', box_text)
      if jadwal:
        matkul_info['jadwal'] = jadwal
      
      # Extract pengampu
      pengampu = re.search(r'PENGAMPU\s*:\s*(.+?)(?:RUANG|$)', box_text)
      if pengampu:
        pengampu_text = pengampu.group(1).strip()
        matkul_info['pengampu'] = [p.strip() for p in pengampu_text.split('&')]
      
      if matkul_info:
        matakuliah_data.append(matkul_info)

    # Method 2: Try to find from navigation or other sources
    if not matakuliah_data:
      # Look for any links that might contain matakuliah info
      all_links = soup.find_all('a', href=True)
      for link in all_links:
        href = link.get('href', '')
        text = link.get_text(strip=True)
        
        # Look for kelas detail links
        if 'kelas/detail' in href and '[' in text:
          match = re.search(r'\[(\w+)\]\s*(.+)', text)
          if match:
            matakuliah_data.append({
              'kode': match.group(1),
              'nama': match.group(2).strip(),
              'link': href
            })

    return Response.Ok({
      'success': True,
      'total': len(matakuliah_data),
      'data': matakuliah_data
    })

  except Exception as e:
    return Response.Error(f"Error fetching matakuliah: {str(e)}")
