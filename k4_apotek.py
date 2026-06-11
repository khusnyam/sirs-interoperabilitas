from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum
import requests
from config import K2_URL

app = FastAPI(title="SILab Prodia", version="1.0.0")

class OrderStatus(str, Enum):
    received   = "received"
    processing = "processing"
    completed  = "completed"
    sent       = "sent"

class Interpretasi(str, Enum):
    normal   = "N"
    high     = "H"
    low      = "L"
    critical = "CR"

# ---- Incoming order dari RS ----
class IncomingLabOrder(BaseModel):
    resourceType: str
    id: str
    status: str
    subject: dict
    requester: Optional[dict] = None
    orderDetail: Optional[List[dict]] = []
    note: Optional[List[dict]] = []

# ---- Hasil satu parameter pemeriksaan ----
class HasilItem(BaseModel):
    nama: str
    nilai: float
    satuan: str
    nilai_normal_min: Optional[float] = None
    nilai_normal_max: Optional[float] = None
    interpretasi: Interpretasi

# ---- Hasil lengkap satu order ----
class HasilCreate(BaseModel):
    order_id: str
    items: List[HasilItem]
    kesimpulan: str
    analis: str = "Laboran Prodia"

class Hasil(HasilCreate):
    id: str
    patient_id: str
    dibuat: datetime

# ============================================================
# DATABASE SEMENTARA
# ============================================================
db_orders: dict = {}
db_hasil:  dict = {}
_hc = 1

def new_hasil_id():
    global _hc
    hid = f"LAB-H{_hc:04d}"
    _hc += 1
    return hid

# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/", tags=["Info"])
def root():
    pending = sum(1 for o in db_orders.values()
                  if o.get("status_local") != "sent")
    return {"sistem": "SILab Prodia", "total_order": len(db_orders),
            "pending_hasil": pending}

# [TERIMA] Order lab dari RS
@app.post("/fhir/ServiceRequest", tags=["Integrasi"])
def terima_order(order: IncomingLabOrder):
    """Menerima order pemeriksaan lab dari Rumah Sakit."""
    data = order.dict()
    data["status_local"] = "received"
    data["diterima"] = str(datetime.now())
    db_orders[order.id] = data
    return {
        "status": "received",
        "order_id": order.id,
        "pesan": f"Order {order.id} diterima, sedang diproses"
    }

@app.get("/orders", tags=["Order"])
def daftar_order():
    return list(db_orders.values())

@app.get("/orders/{order_id}", tags=["Order"])
def ambil_order(order_id: str):
    if order_id not in db_orders:
        raise HTTPException(status_code=404,
            detail=f"Order '{order_id}' tidak ditemukan")
    return db_orders[order_id]

@app.post("/results", status_code=201, tags=["Hasil"])
def input_hasil(data: HasilCreate):
    # TODO: validasi data.order_id ada di db_orders (raise 404 jika tidak).
    #       Buat ID dengan new_hasil_id(), ambil patient_id dari
    #       subject.reference order, simpan Hasil ke db_hasil, dan
    #       set status_local order menjadi "completed". Kembalikan Hasil.
    pass

@app.get("/results", response_model=List[Hasil], tags=["Hasil"])
def daftar_hasil():
    # TODO: kembalikan semua hasil (db_hasil) sebagai list
    pass

@app.get("/results/{order_id}", tags=["Hasil"])
def hasil_per_order(order_id: str):
    # TODO: cari hasil dengan order_id tersebut, raise 404 jika belum ada
    pass

# [INTEGRASI] Kirim hasil ke RS (K2)
@app.post("/kirim-hasil/{order_id}", tags=["Integrasi"])
def kirim_hasil_ke_rs(order_id: str):
    """
    Mengirim DiagnosticReport ke Rumah Sakit setelah hasil jadi.
    """
    hasil_list = [h for h in db_hasil.values()
                  if h.order_id == order_id]
    if not hasil_list:
        raise HTTPException(status_code=404,
            detail=f"Belum ada hasil untuk order '{order_id}'")

    h = hasil_list[0]
    order = db_orders.get(order_id, {})
    patient_ref = order.get("subject", {}).get("reference", "")

    fhir_report = {
        "resourceType": "DiagnosticReport",
        "id": h.id,
        "basedOn": [{"reference": f"ServiceRequest/{order_id}"}],
        "status": "final",
        "category": [{"coding": [{"system": "http://loinc.org",
                                   "code": "11502-2",
                                   "display": "Laboratory report"}]}],
        "subject": {"reference": patient_ref},
        "issued": str(h.dibuat),
        "result": [
            {"display": f"{item.nama}: {item.nilai} {item.satuan} "
                        f"[{item.interpretasi}]"}
            for item in h.items
        ],
        "conclusion": h.kesimpulan
    }

    try:
        resp = requests.post(f"{K2_URL}/fhir/DiagnosticReport",
                             json=fhir_report, timeout=10)
        resp.raise_for_status()
        db_orders[order_id]["status_local"] = "sent"
        return {"status": "hasil_terkirim", "rs_resp": resp.json()}
    except Exception as e:
        return {"status": "gagal", "detail": str(e)}

@app.get("/fhir/DiagnosticReport/{hasil_id}", tags=["FHIR"])
def fhir_report(hasil_id: str):
    # TODO: kembalikan hasil lab dalam format FHIR R4 DiagnosticReport
    #       (resourceType "DiagnosticReport", status "final", subject,
    #       issued, result[], conclusion). Raise 404 jika hasil tidak ada.
    #       Pola payload sama seperti yang dikirim di /kirim-hasil.
    pass
