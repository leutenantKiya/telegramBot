import requests as req
from bs4 import BeautifulSoup as bs
from config import Config

# eclass always use cookies
class Checker:
    @staticmethod
    def isValidCookie(code) -> bool:
        session = req.Session()
        # If code is a dictionary, extract the ukdw_session value
        if isinstance(code, dict):
            code = code.get('ukdw_session', code)
            
        response = session.post("https://eclass.ukdw.ac.id/e-class/id/kelas/index", cookies={'ukdw_session' : code})
        soup = bs(response.text, 'html.parser')
        if soup.find('div', id='login-box-content'):
           return False
        return True
