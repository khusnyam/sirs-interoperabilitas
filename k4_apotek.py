from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum
import requests
from config import K2_URL

app = FastAPI(title="SIApotek Kimia Farma", version="1.0.0")

class DispenseStatus(str, Enum):
    waiting    = "waiting"
    processing = "processing"
    completed  = "completed"
    confirmed  = "confirmed"

# ---- Stok Obat ----
class StokObat(BaseModel):
    nama_obat: str
    kode_obat: Optional[str] = None
    satuan: str = "tablet"
    jumlah: int
    harga_satuan: Optional[float] = None

# ---- Resep masuk dari RS ----
class IncomingPrescription(BaseModel):
    resourceType: str
    id: str
    status: str
    medicationCodeableConcept: dict
    subject: dict
    requester: Optional[dict] = None
    dosageInstruction: Optional[List[dict]] = []
    dispenseRequest: Optional[dict] = None

# ---- Dispense ----
class Dispense(BaseModel):
    id: str
    resep_id: str
    nama_obat: str
    patient_id: str
    jumlah: int
    satuan: str
    status: DispenseStatus
    waktu: datetime
    apoteker: str = "apt-sari-dewi"

# ============================================================
# DATABASE SEMENTARA
# ============================================================
db_stok:    dict = {}
db_resep:   dict = {}
db_dispense:dict = {}
_dc = 1

def new_disp_id():
    global _dc
    did = f"APT-D{_dc:04d}"
    _dc += 1
    return did

# Seed: stok awal obat untuk kasus Hendra
_stok_awal = [
    StokObat(nama_obat="Aspirin 100 mg", kode_obat="ASP100",
             jumlah=500, harga_satuan=500),
    StokObat(nama_obat="Bisoprolol 5 mg", kode_obat="BIS5",
             jumlah=300, harga_satuan=2500),
    StokObat(nama_obat="Atorvastatin 40 mg", kode_obat="ATV40",
             jumlah=200, harga_satuan=3500),
    StokObat(nama_obat="Furosemide 40 mg", kode_obat="FUR40",
             jumlah=400, harga_satuan=1500),
]
for s in _stok_awal:
    db_stok[s.nama_obat.lower()] = s

# ============================================================
# ENDPOINTS
# ============================================================
@app.get("/", tags=["Info"])
def root():
    return {"sistem": "SIApotek Kimia Farma",
            "total_jenis_obat": len(db_stok),
            "resep_pending": sum(1 for r in db_resep.values()
                                 if r.get("status_local") == "waiting")}

@app.get("/stok", tags=["Stok"])
def daftar_stok():
    return list(db_stok.values())

@app.get("/stok/{nama_obat}", tags=["Stok"])
def cek_stok(nama_obat: str):
    key = nama_obat.lower()
    if key not in db_stok:
        raise HTTPException(status_code=404,
            detail=f"Obat '{nama_obat}' tidak ditemukan di stok")
    return db_stok[key]

@app.post("/stok", status_code=201, tags=["Stok"])
def tambah_stok(data: StokObat):
    key = data.nama_obat.lower()
    if key in db_stok:
        db_stok[key].jumlah += data.jumlah
    else:
        db_stok[key] = data
    return db_stok[key]

# [TERIMA] Resep dari RS
@app.post("/fhir/MedicationRequest", tags=["Integrasi"])
def terima_resep(resep: IncomingPrescription):
    """Menerima resep dari Rumah Sakit."""
    data = resep.dict()
    data["status_local"] = "waiting"
    data["diterima"] = str(datetime.now())
    db_resep[resep.id] = data
    return {
        "status": "received",
        "resep_id": resep.id,
        "pesan": "Resep diterima, menunggu proses dispensing"
    }

@app.get("/resep", tags=["Resep"])
def daftar_resep():
    return list(db_resep.values())

@app.get("/resep/{resep_id}", tags=["Resep"])
def ambil_resep(resep_id: str):
    if resep_id not in db_resep:
        raise HTTPException(status_code=404,
            detail=f"Resep '{resep_id}' tidak ditemukan")
    return db_resep[resep_id]

@app.post("/dispense/{resep_id}", status_code=201, tags=["Dispense"])
def proses_dispense(resep_id: str):
    # 1. Validasi resep ada
    if resep_id not in db_resep:
        raise HTTPException(status_code=404,
            detail=f"Resep '{resep_id}' tidak ditemukan")

    resep = db_resep[resep_id]

    # 2. Ambil nama obat & jumlah dari payload resep
    nama_obat = resep.get("medicationCodeableConcept", {}).get("text", "")
    dispense_req = resep.get("dispenseRequest") or {}
    qty_obj = dispense_req.get("quantity") or {}
    jumlah_diminta = int(qty_obj.get("value", 1))
    satuan = qty_obj.get("unit", "tablet")
    patient_ref = resep.get("subject", {}).get("reference", "")
    patient_id = patient_ref.split("/")[-1]

    # 3. Validasi stok
    key = nama_obat.lower()
    if key not in db_stok:
        raise HTTPException(status_code=409,
            detail=f"Obat '{nama_obat}' tidak ada di stok")
    if db_stok[key].jumlah < jumlah_diminta:
        raise HTTPException(status_code=409,
            detail=f"Stok '{nama_obat}' tidak mencukupi "
                   f"(tersisa {db_stok[key].jumlah}, diminta {jumlah_diminta})")

    # 4. Kurangi stok, buat dispense, simpan
    db_stok[key].jumlah -= jumlah_diminta
    did = new_disp_id()
    dispense = Dispense(
        id=did,
        resep_id=resep_id,
        nama_obat=nama_obat,
        patient_id=patient_id,
        jumlah=jumlah_diminta,
        satuan=satuan,
        status=DispenseStatus.completed,
        waktu=datetime.now()
    )
    db_dispense[did] = dispense
    db_resep[resep_id]["status_local"] = "completed"
    return dispense

# [INTEGRASI] Kirim konfirmasi dispense ke RS (K2)
@app.post("/kirim-konfirmasi/{dispense_id}", tags=["Integrasi"])
def kirim_konfirmasi(dispense_id: str):
    """Konfirmasi ke RS bahwa obat sudah diserahkan ke pasien."""
    if dispense_id not in db_dispense:
        raise HTTPException(status_code=404,
            detail=f"Record dispense '{dispense_id}' tidak ditemukan")

    d = db_dispense[dispense_id]
    fhir_dispense = {
        "resourceType": "MedicationDispense",
        "id": dispense_id,
        "basedOn": [{"reference": f"MedicationRequest/{d.resep_id}"}],
        "status": "completed",
        "medicationCodeableConcept": {"text": d.nama_obat},
        "subject": {"reference": f"Patient/{d.patient_id}"},
        "performer": [{"actor": {
            "reference": "Organization/apotek-kimia-farma",
            "display": "Apotek Kimia Farma Kaliurang"
        }}],
        "quantity": {"value": d.jumlah, "unit": d.satuan},
        "whenHandedOver": str(d.waktu)
    }

    try:
        resp = requests.post(f"{K2_URL}/fhir/MedicationDispense",
                             json=fhir_dispense, timeout=10)
        resp.raise_for_status()
        db_dispense[dispense_id].status = DispenseStatus.confirmed
        return {"status": "konfirmasi_terkirim", "rs_resp": resp.json()}
    except Exception as e:
        return {"status": "gagal", "detail": str(e)}

@app.get("/fhir/MedicationDispense/{dispense_id}", tags=["FHIR"])
def fhir_dispense(dispense_id: str):
    if dispense_id not in db_dispense:
        raise HTTPException(status_code=404,
            detail=f"Record dispense '{dispense_id}' tidak ditemukan")
    d = db_dispense[dispense_id]
    return {
        "resourceType": "MedicationDispense",
        "id": dispense_id,
        "basedOn": [{"reference": f"MedicationRequest/{d.resep_id}"}],
        "status": "completed",
        "medicationCodeableConcept": {"text": d.nama_obat},
        "subject": {"reference": f"Patient/{d.patient_id}"},
        "performer": [{"actor": {
            "reference": "Organization/apotek-kimia-farma",
            "display": "Apotek Kimia Farma Kaliurang"
        }}],
        "quantity": {"value": d.jumlah, "unit": d.satuan},
        "whenHandedOver": str(d.waktu)
    }