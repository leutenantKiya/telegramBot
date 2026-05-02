import cloudscraper
class Config: 
    BASE_URL = "https://eclass.ukdw.ac.id"
    LOGIN_URL = BASE_URL + "/id/home/do_login"
    KELAS_URL = BASE_URL + "/e-class/id/kelas/index"
    MATERI_URL = BASE_URL + "/e-class/id/materi/index"
    TUGAS_URL = BASE_URL + "/e-class/id/kelas/tugas"
    TUGAS_DETAIL_URL = BASE_URL + "/e-class/id/kelas/detail_tugas"
    PENGUMUMAN_URL = BASE_URL + "/e-class/id/pengumuman/baca"
    PRESENSI_URL = BASE_URL + "/e-class/id/kelas/presensi"
    DISKUSI_URL = BASE_URL + "/e-class/id/kelas/detail"
    
    @staticmethod
    def create_session():
        return cloudscraper.create_scraper()
    