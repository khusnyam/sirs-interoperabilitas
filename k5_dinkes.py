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
    laporan = list(db_laporan.values())

    if not laporan:
        return {
            "total_kasus": 0,
            "kasus_dirujuk": 0,
            "kasus_rawat_inap": 0,
            "rata_usia": 0,
            "gender_male": 0,
            "gender_female": 0,
            "periode": {
                "pertama": None,
                "terakhir": None
            }
        }

    tanggal_list = sorted(l.tanggal for l in laporan)

    return {
        "total_kasus": len(laporan),
        "kasus_dirujuk": sum(1 for l in laporan if l.dirujuk),
        "kasus_rawat_inap": sum(1 for l in laporan if l.rawat_inap),
        "rata_usia": round(sum(l.usia for l in laporan) / len(laporan), 1),
        "gender_male": sum(1 for l in laporan if l.jenis_kelamin.lower() in ("l", "laki-laki", "male")),
        "gender_female": sum(1 for l in laporan if l.jenis_kelamin.lower() in ("p", "perempuan", "female")),
        "periode": {
            "pertama": tanggal_list[0],
            "terakhir": tanggal_list[-1]
        }
    }

@app.get("/dashboard/per-icd10", tags=["Dashboard"])
def per_icd10():
    hitung = defaultdict(lambda: {"jumlah": 0, "diagnosis_display": ""})

    for l in db_laporan.values():
        hitung[l.diagnosis_icd10]["jumlah"] += 1
        hitung[l.diagnosis_icd10]["diagnosis_display"] = l.diagnosis_display

    return [
        {
            "icd10": kode,
            "diagnosis_display": data["diagnosis_display"],
            "jumlah": data["jumlah"]
        }
        for kode, data in sorted(hitung.items(), key=lambda x: -x[1]["jumlah"])
    ]

@app.get("/dashboard/per-kecamatan", tags=["Dashboard"])
def per_kecamatan():
    hitung = defaultdict(int)

    for l in db_laporan.values():
        hitung[l.kecamatan] += 1

    return [
        {"kecamatan": kec, "jumlah": jumlah}
        for kec, jumlah in sorted(hitung.items(), key=lambda x: -x[1])
    ]

@app.get("/dashboard/per-sumber", tags=["Dashboard"])
def per_sumber():
    hitung = defaultdict(int)

    for l in db_laporan.values():
        hitung[l.sumber] += 1

    return [
        {"sumber": sumber, "jumlah": jumlah}
        for sumber, jumlah in sorted(hitung.items(), key=lambda x: -x[1])
    ]

@app.get("/dashboard/tren-harian", tags=["Dashboard"])
def tren_harian():
    hitung = defaultdict(int)

    for l in db_laporan.values():
        hitung[l.tanggal] += 1

    return [
        {"tanggal": tgl, "jumlah": jumlah}
        for tgl, jumlah in sorted(hitung.items())
    ]