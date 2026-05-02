from typing import Any, Dict, Optional

from config import Config
from datetime import datetime
from bs4 import BeautifulSoup as bs
from utils.checker import Checker
from utils.response import Response
from fastapi import APIRouter, Body

presensi_bp = APIRouter()

@presensi_bp.post('/{id}')
def presensi(id: str, data: Optional[Dict[str, Any]] = Body(default=None)):
  try:
    data = data or {}
    session = Config.create_session()

    if not id:
      return Response.Error("Kelas ID is required")
    if not data.get('cookies'):
      return Response.Error('Cookies are required')

    cookies = data.get('cookies')
    if isinstance(cookies, dict):
        cookies = cookies.get('ukdw_session', str(cookies))

    if not Checker.isValidCookie(cookies):
      return Response.Error('Invalid cookies')

    response = session.post(Config.PRESENSI_URL + f"/{id}", cookies={'ukdw_session': cookies})

    if response.ok:
      soup = bs(response.text, 'html.parser')

      form = soup.find('form')
      if not form:
        return Response.Error("Presensi belum tersedia")

      td_element = soup.findAll('td')
      b_element = td_element[6].find('b')

      if not b_element:
        return Response.Error("Presensi belum tersedia")

      raw_text = b_element.text.strip()

      date_obj = None
      time_obj = None
      title = None
      
      parts = raw_text.split("||")
      if len(parts) == 2:
        date_time_part = parts[0].strip()
        title = parts[1].strip()
        date_part, time_part = date_time_part.split(", Pukul :")
        date_obj = datetime.strptime(date_part.strip(), "%d %b %Y").date()
        time_obj = datetime.strptime(time_part.strip(), "%H:%M").time()

      p_pertemuanke_input = form.find('input', {'name': 'p_pertemuanke'})
      p_idpresensi_input = form.find('input', {'name': 'p_idpresensi'})

      if not p_pertemuanke_input or not p_idpresensi_input:
        return Response.Error({
          "message": "Presensi belum terbuka atau sudah ditutup",
          "sessionDate": date_obj.strftime("%Y-%m-%d") if date_obj else None,
          "sessionTime": time_obj.strftime("%H:%M") if time_obj else None,
          "sessionTitle": title,
          "isSessionOpen": False if not p_pertemuanke_input else True
        })

      p_pertemuanke = p_pertemuanke_input.get('value')
      p_idpresensi = p_idpresensi_input.get('value')

      post_data = {
        'presensi_hadir': 'HADIR',
        'p_pertemuanke': p_pertemuanke,
        'p_idpresensi': p_idpresensi
      }

      res = session.post(Config.PRESENSI_URL + f"/{id}", cookies={'ukdw_session': cookies}, data=post_data)

      if res.ok:
        return Response.Ok({
          "message": "Presensi berhasil",
          "sessionDate": date_obj.strftime("%Y-%m-%d") if date_obj else None,
          "sessionTime": time_obj.strftime("%H:%M") if time_obj else None,
          "sessionTitle": title,
          "isSessionOpen": False if not p_pertemuanke_input else True
        })
      else:
        return Response.Error("Presensi gagal")
    return Response.Error("Presensi not found")
  except Exception as e:
    return Response.Error(str(e))