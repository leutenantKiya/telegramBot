from fastapi import FastAPI
from config import Config  # all end points registered
from utils.response import Response
from routes import login_bp, matakuliah_bp, presensi_bp, materi_bp

app = FastAPI(title="UKDW API")
app.state.config = Config

app.include_router(login_bp, prefix='/api/v1/login')
app.include_router(matakuliah_bp, prefix='/api/v1/matakuliah')
app.include_router(presensi_bp, prefix='/api/v1/presensi')
app.include_router(materi_bp, prefix='/api/v1/materi')


@app.get('/')
def index():
    return Response.Ok({
        "name" : "UKDW API",
        "version" : "1.0.0",
        "endpoints" : {
            "login" : "/api/v1/login",
            "matakuliah" :  "/api/v1/matakuliah",
            "presensi" : "/api/v1/presensi/{id}",
            "materi" : "/api/v1/materi/{id}"
        }
    })
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("request_handler:app", host="127.0.0.1", port=8000, reload=True)