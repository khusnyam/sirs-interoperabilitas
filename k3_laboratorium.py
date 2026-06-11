from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, validator
from typing import Optional, List
from datetime import date, datetime
from enum import Enum
import requests
from config import K2_URL, K5_URL

app = FastAPI(title="SIMPUS Depok III", version="1.0.0")

# ---- Enumerasi ----
class Gender(str, Enum):
    male    = "male"
    female  = "female"
    other   = "other"
    unknown = "unknown"

# ---- Model Pasien ----
class PatientCreate(BaseModel):
    nik: str
    nama_depan: str
    nama_belakang: str
    tanggal_lahir: date
    jenis_kelamin: Gender
    telepon: Optional[str] = None
    alamat: Optional[str] = None
    kecamatan: Optional[str] = None

    @validator('tanggal_lahir')
    def tgl_valid(cls, v):
        if v > date.today():
            raise ValueError('Tanggal lahir tidak boleh masa depan')
        return v

class Patient(PatientCreate):
    id: str
    terdaftar: datetime

# ---- Model Tanda Vital ----
class VitalCreate(BaseModel):
    patient_id: str
    td_sistolik: float   # mmHg
    td_diastolik: float  # mmHg
    nadi: Optional[float] = None    # /menit
    spo2: Optional[float] = None    # %
    suhu: Optional[float] = None    # Celsius
    catatan: Optional[str] = None

class Vital(VitalCreate):
    id: str
    waktu: datetime

# ---- Model Diagnosis Awal ----
class ConditionCreate(BaseModel):
    patient_id: str
    icd10_code: str
    display: str
    severity: Optional[str] = None  # mild/moderate/severe
    catatan: Optional[str] = None

class Condition(ConditionCreate):
    id: str
    recorded: datetime

# ---- Model Rujukan ----
class RujukanCreate(BaseModel):
    patient_id: str
    condition_id: str
    alasan: str
    rs_tujuan: str = "rsup-sardjito"
    prioritas: str = "urgent"  # routine/urgent/asap/stat

class Rujukan(RujukanCreate):
    id: str
    dibuat: datetime
    status: str = "sent"

# ============================================================
# DATABASE SEMENTARA
# ============================================================
db_pasien:    dict = {}
db_vital:     dict = {}
db_kondisi:   dict = {}
db_rujukan:   dict = {}
_p = _v = _c = _r = 1

def nid(prefix, counter_dict):
    if prefix not in counter_dict:
        counter_dict[prefix] = 1
    current_val = counter_dict[prefix]
    counter_dict[prefix] += 1
    return f"{prefix}{current_val:04d}"

_pc = 1
def new_patient_id():
    global _pc
    pid = f"PKM-P{_pc:04d}"
    _pc += 1
    return pid

_vc = 1
def new_vital_id():
    global _vc
    vid = f"PKM-V{_vc:04d}"
    _vc += 1
    return vid

_cc = 1
def new_cond_id():
    global _cc
    cid = f"PKM-C{_cc:04d}"
    _cc += 1
    return cid

_rc = 1
def new_rujukan_id():
    global _rc
    rid = f"PKM-R{_rc:04d}"
    _rc += 1
    return rid

# Seed data: Bapak Hendra
_hendra = PatientCreate(
    nik="3404012205790001",
    nama_depan="Hendra",
    nama_belakang="Kusuma",
    tanggal_lahir=date(1979, 5, 22),
    jenis_kelamin=Gender.male,
    telepon="081234567899",
    alamat="Jl. Kaliurang Km 7 No. 15",
    kecamatan="Depok"
)
_hid = new_patient_id()
db_pasien[_hid] = Patient(id=_hid, **_hendra.dict(),
                           terdaftar=datetime.now())

# ============================================================
# ENDPOINT: PASIEN
# ============================================================
@app.get("/", tags=["Info"])
def root():
    return {
        "sistem": "SIMPUS Puskesmas Depok III",
        "port": 8001,
        "total_pasien": len(db_pasien),
        "total_rujukan": len(db_rujukan)
    }

@app.post("/patients", response_model=Patient,
          status_code=201, tags=["Pasien"])
def daftarkan_pasien(data: PatientCreate):
    pid = new_patient_id()
    pasien_baru = Patient(
        id=pid,
        **data.dict(),
        terdaftar=datetime.now()
    )
    db_pasien[pid] = pasien_baru
    return pasien_baru

@app.get("/patients", response_model=List[Patient], tags=["Pasien"])
def daftar_pasien():
    return list(db_pasien.values())

@app.get("/patients/{patient_id}", response_model=Patient, tags=["Pasien"])
def ambil_pasien(patient_id: str):
    if patient_id not in db_pasien:
        raise HTTPException(status_code=404, detail=f"Pasien dengan ID {patient_id} tidak ditemukan")
    return db_pasien[patient_id]

@app.get("/fhir/Patient/{patient_id}", tags=["FHIR"])
def fhir_patient(patient_id: str):
    if patient_id not in db_pasien:
        raise HTTPException(status_code=404, detail=f"Pasien dengan ID {patient_id} tidak ditemukan")
    
    p = db_pasien[patient_id]

    fhir_resource = {
        "resourceType": "Patient",
        "id": p.id,
        "active": True,
        "identifier": [
            {
                "use": "official",
                "system": "https://fhir.kemkes.go.id/id/nik",
                "value": p.nik
            }
        ],
        "name": [
            {
                "use": "official",
                "text": f"{p.nama_depan} {p.nama_belakang}".strip(),
                "family": p.nama_belakang,
                "given": [p.nama_depan]
            }
        ],
        "gender": p.jenis_kelamin.value,
        "birthDate": str(p.tanggal_lahir),
        "telecom": [
            {
                "system": "phone",
                "value": p.telepon,
                "use": "mobile"
            }
        ] if p.telepon else [],
        "address": [
            {
                "use": "home",
                "line": [p.alamat] if p.alamat else [],
                "district": p.kecamatan if p.kecamatan else ""
            }
        ] if (p.alamat or p.kecamatan) else []
    }
    
    return fhir_resource

# ============================================================
# ENDPOINT: TANDA VITAL
# ============================================================
@app.post("/vitals", response_model=Vital,
          status_code=201, tags=["Tanda Vital"])
def catat_vital(data: VitalCreate):
    if data.patient_id not in db_pasien:
        raise HTTPException(status_code=404, detail=f"Pasien dengan ID {data.patient_id} tidak ditemukan")
    vid = new_vital_id()
    vital_baru = Vital(
        id=vid,
        **data.dict(),
        waktu=datetime.now()
    )
    db_vital[vid] = vital_baru
    return vital_baru

@app.get("/patients/{patient_id}/vitals",
         response_model=List[Vital], tags=["Tanda Vital"])
def ambil_vital_pasien(patient_id: str):
    if patient_id not in db_pasien:
        raise HTTPException(status_code=404, detail=f"Pasien dengan ID {patient_id} tidak ditemukan")
    vitals_pasien = [v for v in db_vital.values() if v.patient_id == patient_id]
    return vitals_pasien

# ============================================================
# ENDPOINT: DIAGNOSIS
# ============================================================
@app.post("/conditions", response_model=Condition,
          status_code=201, tags=["Diagnosis"])
def catat_diagnosis(data: ConditionCreate):
    if data.patient_id not in db_pasien:
        raise HTTPException(status_code=404, detail=f"Pasien dengan ID {data.patient_id} tidak ditemukan")
    cid = new_cond_id()
    kondisi_baru = Condition(
        id=cid,
        **data.dict(),
        recorded=datetime.now()
    )
    db_kondisi[cid] = kondisi_baru
    return kondisi_baru

# ============================================================
# INTEGRASI 1: Kirim Rujukan ke Rumah Sakit (K2)
# ============================================================
@app.post("/rujukan", response_model=Rujukan,
          status_code=201, tags=["Integrasi"])
def kirim_rujukan(data: RujukanCreate):
    """
    Membuat surat rujukan dan mengirimkannya ke API Rumah Sakit.
    Jika RS tidak bisa dijangkau, rujukan tetap tersimpan lokal.
    """
    # Pastikan pasien ada
    if data.patient_id not in db_pasien:
        raise HTTPException(status_code=404,
            detail=f"Pasien '{data.patient_id}' tidak ditemukan")

    # Buat objek rujukan lokal
    rid = new_rujukan_id()
    pasien = db_pasien[data.patient_id]
    kondisi = db_kondisi.get(data.condition_id)

    rujukan = Rujukan(id=rid, **data.dict(), dibuat=datetime.now())
    db_rujukan[rid] = rujukan

    # Siapkan payload FHIR ServiceRequest
    fhir_payload = {
        "resourceType": "ServiceRequest",
        "id": rid,
        "status": "active",
        "intent": "order",
        "priority": data.prioritas,
        "subject": {
            "reference": f"Patient/{data.patient_id}",
            "display": f"{pasien.nama_depan} {pasien.nama_belakang}"
        },
        "requester": {
            "reference": "Organization/puskesmas-depok-3",
            "display": "Puskesmas Depok III"
        },
        "performer": [
            {"reference": f"Organization/{data.rs_tujuan}"}
        ],
        "reasonCode": [
            {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10",
                         "code": kondisi.icd10_code if kondisi else "Z99",
                         "display": kondisi.display if kondisi else ""}]}
        ],
        "note": [{"text": data.alasan}]
    }

    # Kirim ke RS
    try:
        rs_resp = requests.post(
            f"{K2_URL}/fhir/ServiceRequest",
            json=fhir_payload, timeout=10
        )
        rs_resp.raise_for_status()
        rujukan.status = "delivered"
    except Exception:
        rujukan.status = "pending"  # tersimpan lokal, belum terkirim

    return rujukan

# ============================================================
# INTEGRASI 2: Laporan Kasus ke Dinas Kesehatan (K5)
# ============================================================
@app.post("/laporan-kasus", tags=["Integrasi"])
def laporan_ke_dinkes(patient_id: str, condition_id: str):
    """
    Mengirim notifikasi kasus ke Dinas Kesehatan untuk surveilans.
    """
    if patient_id not in db_pasien:
        raise HTTPException(status_code=404,
            detail=f"Pasien '{patient_id}' tidak ditemukan")

    pasien = db_pasien[patient_id]
    kondisi = db_kondisi.get(condition_id)
    usia = (date.today() - pasien.tanggal_lahir).days // 365

    payload = {
        "sumber": "puskesmas-depok-3",
        "jenis_laporan": "kasus_baru",
        "tanggal": str(date.today()),
        "pasien_id": patient_id,
        "usia": usia,
        "jenis_kelamin": pasien.jenis_kelamin,
        "diagnosis_icd10": kondisi.icd10_code if kondisi else "Z99",
        "diagnosis_display": kondisi.display if kondisi else "",
        "kecamatan": pasien.kecamatan or "Tidak diketahui",
        "kabupaten": "Sleman",
        "dirujuk": len(db_rujukan) > 0
    }

    try:
        resp = requests.post(
            f"{K5_URL}/api/laporan-kasus",
            json=payload, timeout=10
        )
        resp.raise_for_status()
        return {"status": "laporan_terkirim", "dinkes_id": resp.json().get("id")}
    except Exception as e:
        return {"status": "gagal", "detail": str(e)}

@app.get("/rujukan", response_model=List[Rujukan], tags=["Integrasi"])
def daftar_rujukan():
    return list(db_rujukan.values())
