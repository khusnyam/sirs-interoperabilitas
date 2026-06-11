from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from collections import defaultdict

app = FastAPI(
    title="SiSurv Dinkes Sleman",
    description="Sistem Surveilans Penyakit Dinas Kesehatan Sleman",
    version="1.0.0"
)

# ============================================================
# MODEL
# ============================================================
class LaporanKasus(BaseModel):
    sumber: str              # "puskesmas-depok-3", "rsup-sardjito", dll
    jenis_laporan: str
    tanggal: str             # YYYY-MM-DD
    pasien_id: str
    usia: int
    jenis_kelamin: str
    diagnosis_icd10: str
    diagnosis_display: str
    kecamatan: str
    kabupaten: str = "Sleman"
    dirujuk: Optional[bool] = False
    rawat_inap: Optional[bool] = False
    catatan: Optional[str] = None

class LaporanRecord(LaporanKasus):
    id: str
    diterima: datetime

# ============================================================
# DATABASE
# ============================================================
db_laporan: dict = {}
_lc = 1

def new_lap_id():
    global _lc
    lid = f"DK-{_lc:05d}"
    _lc += 1
    return lid

# ============================================================
# ENDPOINTS
# ============================================================
@app.get("/", tags=["Info"])
def root():
    return {
        "sistem": "SiSurv Dinkes Sleman",
        "total_laporan": len(db_laporan),
        "dashboard": "/dashboard"
    }

@app.post("/api/laporan-kasus", status_code=201, tags=["Laporan"])
def terima_laporan(data: LaporanKasus):
    """
    Menerima laporan kasus dari fasilitas kesehatan manapun.
    Endpoint ini dipanggil oleh K1 (Puskesmas) dan K2 (RS).
    """
    lid = new_lap_id()
    record = LaporanRecord(id=lid, **data.dict(), diterima=datetime.now())
    db_laporan[lid] = record
    return {
        "id": lid,
        "status": "diterima",
        "pesan": f"Laporan dari '{data.sumber}' berhasil dicatat"
    }

@app.get("/api/laporan-kasus",
         response_model=List[LaporanRecord], tags=["Laporan"])
def semua_laporan(sumber: Optional[str] = None,
                  tanggal: Optional[str] = None):
    hasil = list(db_laporan.values())
    if sumber:
        hasil = [l for l in hasil if l.sumber == sumber]
    if tanggal:
        hasil = [l for l in hasil if l.tanggal == tanggal]
    return hasil

@app.get("/dashboard", tags=["Dashboard"])
def dashboard():
    # TODO: hitung statistik agregat dari db_laporan dan kembalikan, mis.
    #       total_kasus, kasus_dirujuk, kasus_rawat_inap, rata_usia,
    #       gender_male, gender_female, dan periode (tanggal pertama/terakhir).
    #       Tangani kasus belum ada laporan (kembalikan total 0).
    pass

@app.get("/dashboard/per-icd10", tags=["Dashboard"])
def per_icd10():
    # TODO: kelompokkan db_laporan berdasarkan diagnosis_icd10 dan hitung
    #       jumlah tiap diagnosis (gunakan defaultdict). Kembalikan list.
    pass

@app.get("/dashboard/per-kecamatan", tags=["Dashboard"])
def per_kecamatan():
    # TODO: kelompokkan db_laporan berdasarkan kecamatan, hitung jumlahnya
    pass

@app.get("/dashboard/per-sumber", tags=["Dashboard"])
def per_sumber():
    # TODO: kelompokkan db_laporan berdasarkan sumber (faskes pengirim)
    pass

@app.get("/dashboard/tren-harian", tags=["Dashboard"])
def tren_harian():
    # TODO: hitung jumlah kasus baru per tanggal, urutkan berdasarkan tanggal
    pass
