import re
from typing import Any, Dict, Optional

from config import Config
from bs4 import BeautifulSoup as bs
from utils.response import Response
from fastapi import APIRouter, Body

login_bp = APIRouter()

@login_bp.post('/')
def login(data: Optional[Dict[str, Any]] = Body(default=None)):
  try:
    data = data or {}
    session = Config.create_session()

    if not data.get('id') or not data.get('password'):
      return Response.Error('ID and Password are required')

    form_data = {
      'id': data.get('id'),
      'password': data.get('password')
    }

    response = session.post(Config.LOGIN_URL, data=form_data)

    if "_cf_chl_opt" in response.text or "Just a moment" in response.text:
      return Response.Error("Blocked by Cloudflare protection. Please try again later.", code=Response.HTTP_FORBIDDEN)

    soup = bs(response.text, 'html.parser')
    error = soup.find('div', {
      'id': 'error'
    })

    if error:
      return Response.Error(error.text)

    if response.ok:
      match = re.search(r'\[([\d]+)\]\s+([^\n]+)', response.text)
      if match:
        user_id = match.group(1)
        user_name = match.group(2).strip()
        user_name = re.sub(r'</?[^>]+>', '', user_name)
        user_name = user_name.strip()
        full_user_info = f"[{user_id}] {user_name}"
      else:
        full_user_info = "Unknown User"

      return Response.Ok({
        "message": f"Logged in as {full_user_info}",
        "cookies": session.cookies.get_dict()
      })

    return Response.Error("Login failed")
  except Exception as e:
    return Response.Error(str(e))