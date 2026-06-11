from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import date, datetime
from enum import Enum
import requests
from config import K3_URL, K4_URL, K5_URL

app = FastAPI(title="SIMRS Sardjito", version="1.0.0")

class Gender(str, Enum):
    male = "male"; female = "female"
    other = "other"; unknown = "unknown"

class AdmissionStatus(str, Enum):
    active    = "active"
    discharged= "discharged"
    referred  = "referred"

# ---- Patient (sama seperti K1 tapi prefix berbeda) ----
class PatientCreate(BaseModel):
    nik: str
    nama_depan: str
    nama_belakang: str
    tanggal_lahir: date
    jenis_kelamin: Gender
    telepon: Optional[str] = None
    sumber_rujukan: Optional[str] = None  # "puskesmas-depok-3" dll

class Patient(PatientCreate):
    id: str
    terdaftar: datetime
    status: AdmissionStatus = AdmissionStatus.active

# ---- ServiceRequest yang masuk dari Puskesmas ----
class IncomingReferral(BaseModel):
    resourceType: str
    id: str
    status: str
    priority: Optional[str] = "routine"
    subject: dict
    requester: dict
    performer: Optional[List[dict]] = []
    reasonCode: Optional[List[dict]] = []
    note: Optional[List[dict]] = []

# ---- Order Lab ----
class LabOrderCreate(BaseModel):
    patient_id: str
    pemeriksaan: List[str]  # daftar nama pemeriksaan
    catatan: Optional[str] = None

class LabOrder(LabOrderCreate):
    id: str
    dibuat: datetime
    status: str = "pending"

# ---- Hasil Lab (masuk dari K3) ----
class IncomingDiagnosticReport(BaseModel):
    resourceType: str
    id: str
    basedOn: Optional[List[dict]] = []
    status: str
    subject: dict
    issued: str
    result: List[dict]
    conclusion: Optional[str] = None

# ---- Diagnosis ----
class ConditionCreate(BaseModel):
    patient_id: str
    icd10_code: str
    display: str
    jenis: str = "awal"  # "awal" atau "final"
    catatan: Optional[str] = None

class Condition(ConditionCreate):
    id: str
    recorded: datetime

# ---- Observasi / Tanda Vital di IGD ----
class ObservationCreate(BaseModel):
    patient_id: str
    td_sistolik: Optional[float] = None
    td_diastolik: Optional[float] = None
    nadi: Optional[float] = None
    spo2: Optional[float] = None
    suhu: Optional[float] = None
    catatan: Optional[str] = None

class Observation(ObservationCreate):
    id: str
    waktu: datetime

# ---- Resep ----
class MedicationCreate(BaseModel):
    patient_id: str
    nama_obat: str
    dosis: str
    frekuensi: str
    rute: str = "oral"
    durasi_hari: int
    catatan: Optional[str] = None

class Medication(MedicationCreate):
    id: str
    prescriber: str = "dr-kardiologi-001"
    dibuat: datetime
    status: str = "active"

# ---- Dispense Konfirmasi (masuk dari K4) ----
class IncomingDispense(BaseModel):
    resourceType: str
    id: str
    basedOn: Optional[List[dict]] = []
    status: str
    subject: dict
    quantity: dict
    whenHandedOver: str

# ============================================================
# DATABASE SEMENTARA
# ============================================================
db_pasien:    dict = {}
db_rujukan:   dict = {}   # rujukan masuk dari Puskesmas
db_lab_orders:dict = {}
db_lab_results:dict = {}
db_kondisi:   dict = {}
db_meds:      dict = {}
db_dispense:  dict = {}
db_observations:dict = {}  # tanda vital di IGD

_pc = 2   # mulai dari 2; RS-P00001 sudah dipakai seed Hendra
_lc = 1
_cc = 1
_mc = 1
_oc = 1

def new_patient_id():
    global _pc
    pid = f"RS-P{_pc:05d}"; _pc += 1; return pid

def new_cond_id():
    global _cc
    cid = f"RS-C{_cc:04d}"; _cc += 1; return cid

def new_med_id():
    global _mc
    mid = f"RS-RX{_mc:04d}"; _mc += 1; return mid

def new_obs_id():
    global _oc
    oid = f"RS-O{_oc:04d}"; _oc += 1; return oid

# Seed: admit Hendra langsung (data sudah di-refer dari PKM)
_hendra = Patient(
    id="RS-P00001", nik="3404012205790001",
    nama_depan="Hendra", nama_belakang="Kusuma",
    tanggal_lahir=date(1979, 5, 22),
    jenis_kelamin=Gender.male,
    sumber_rujukan="puskesmas-depok-3",
    terdaftar=datetime.now()
)
db_pasien["RS-P00001"] = _hendra

# ============================================================
# ENDPOINT DASAR RUMAH SAKIT
# ============================================================
@app.get("/", tags=["Info"])
def root():
    return {
        "sistem": "SIMRS Sardjito",
        "total_pasien": len(db_pasien),
        "rujukan_masuk": len(db_rujukan),
        "lab_order": len(db_lab_orders),
        "resep": len(db_meds)
    }

@app.post("/patients", response_model=Patient,
          status_code=201, tags=["Pasien"])
def admit_pasien(data: PatientCreate):
    id = new_patient_id()
    patient = Patient(id=new_patient_id(), terdaftar=datetime.now(), **data.dict())
    db_pasien[id]=patient
    return patient

    # # TODO: buat ID dengan new_patient_id(), bungkus jadi Patient,
    # #       simpan ke db_pasien, lalu kembalikan objek Patient

@app.get("/patients/{patient_id}", response_model=Patient, tags=["Pasien"])
def ambil_pasien(patient_id: str):
    if patient_id not in db_pasien:
        raise HTTPException (status_code=404,
                             detail=f"Pasien '{patient_id}' tidak ditemukan")
    return db_pasien[patient_id]

@app.get("/fhir/Patient/{patient_id}", tags=["FHIR"])
def fhir_patient(patient_id: str):
    if patient_id not in db_pasien :
        raise HTTPException ( 
            status_code =404,
            detail = f"Pasien ’{patient_id}’ tidak ditemukan"
        )
    p = db_pasien[patient_id]
    return {
        "resourceType": "Patient", 
        "id": p.id,
        "identifier": [
            {"system ": "https://www.dukcapil.go.id", "value ": p.nik}],
        "name": [{"use": "official", "family": p.nama_belakang,
                  "given": p.nama_depan}],
        "gender": p.jenis_kelamin,
        "birthDate": str(p.tanggal_lahir)
    }

@app.get("/admissions", tags=["Pasien"])
def daftar_admissions():
    return {
        "total_pasien": len(db_pasien),
        "total_rujukan_masuk": len(db_rujukan),
        "pasien": list(db_pasien.values()),
        "rujukan": list(db_rujukan.values())
    }
    # TODO: kembalikan rujukan yang masuk (db_rujukan) dan pasien
    #       yang sudah di-admit (db_pasien)

@app.post("/observations", status_code=201, tags=["Observasi"])
def catat_observasi(data: ObservationCreate):
    if data.patient_id not in db_pasien:
        raise HTTPException(status_code=404, detail="Pasien tidak ditemukan")
    oid = new_obs_id()
    obs = Observation(id=oid, waktu=datetime.now(), **data.dict())
    db_observations[oid] = obs
    return obs

@app.post("/conditions", response_model=Condition,
          status_code=201, tags=["Diagnosis"])
def catat_diagnosis(data: ConditionCreate):
    if data.patient_id not in db_pasien:
        raise HTTPException(status_code=404, detail="Pasien tidak ditemukan")
    cid = new_cond_id()
    kondisi = Condition(id=cid, recorded=datetime.now(), **data.dict())
    db_kondisi[cid] = kondisi
    return kondisi
    # TODO: validasi patient_id ada, buat ID dengan new_cond_id(),
    #       simpan Condition ke db_kondisi, kembalikan

@app.post("/medications", response_model=Medication,
          status_code=201, tags=["Resep"])
def tulis_resep(data: MedicationCreate):
    if data.patient_id not in db_pasien:
        raise HTTPException(status_code=404,
            detail=f"Pasien '{data.patient_id}' tidak ditemukan")
    mid = new_med_id()
    obat = Medication(id=mid, dibuat=datetime.now(), **data.dict())  
    db_meds[mid] = obat
    return obat
    # TODO: validasi patient_id ada, buat ID dengan new_med_id(),
    #       simpan Medication ke db_meds, kembalikan
    #       (resep ini nanti dikirim ke apotek lewat /kirim-resep/{med_id})


# ============================================================
# [TERIMA] Rujukan masuk dari Puskesmas
# ============================================================
@app.post("/fhir/ServiceRequest", tags=["Integrasi"])
def terima_rujukan(referral: IncomingReferral):
    """
    Endpoint ini dipanggil oleh Puskesmas (K1) ketika mengirim rujukan.
    """
    db_rujukan[referral.id] = referral.dict()
    return {
        "status": "received",
        "message": f"Rujukan {referral.id} diterima oleh RSUP Sardjito",
        "admission_queue": len(db_rujukan)
    }

# ============================================================
# [INTEGRASI] Order Lab ke Laboratorium (K3)
# ============================================================
@app.post("/order-lab", status_code=201, tags=["Integrasi"])
def order_lab(data: LabOrderCreate):
    """
    Membuat order pemeriksaan lab dan mengirimkannya ke Laboratorium.
    """
    if data.patient_id not in db_pasien:
        raise HTTPException(status_code=404,
            detail=f"Pasien '{data.patient_id}' tidak ditemukan")

    global _lc
    lid = f"RS-LAB{_lc:04d}"
    _lc += 1
    order = LabOrder(id=lid, **data.dict(), dibuat=datetime.now())
    db_lab_orders[lid] = order

    pasien = db_pasien[data.patient_id]
    fhir_payload = {
        "resourceType": "ServiceRequest",
        "id": lid,
        "status": "active",
        "intent": "order",
        "category": [{"coding": [
            {"system": "http://snomed.info/sct",
             "code": "108252007", "display": "Laboratory procedure"}
        ]}],
        "code": {"text": ", ".join(data.pemeriksaan)},
        "subject": {
            "reference": f"Patient/{data.patient_id}",
            "display": f"{pasien.nama_depan} {pasien.nama_belakang}"
        },
        "requester": {"reference": "Practitioner/dr-kardiologi-001"},
        "orderDetail": [{"text": p} for p in data.pemeriksaan],
        "note": [{"text": data.catatan or ""}]
    }

    try:
        resp = requests.post(f"{K3_URL}/fhir/ServiceRequest",
                             json=fhir_payload, timeout=10)
        resp.raise_for_status()
        order.status = "sent"
    except Exception:
        order.status = "pending"

    return order

# ============================================================
# [TERIMA] Hasil Lab dari Laboratorium (K3)
# ============================================================
@app.post("/fhir/DiagnosticReport", tags=["Integrasi"])
def terima_hasil_lab(report: IncomingDiagnosticReport):
    """
    Endpoint ini dipanggil oleh Laboratorium (K3) ketika hasil sudah jadi.
    """
    db_lab_results[report.id] = report.dict()
    return {
        "status": "received",
        "report_id": report.id,
        "conclusion": report.conclusion
    }

@app.get("/lab-results/{patient_id}", tags=["Lab"])
def lihat_hasil_lab(patient_id: str):
    hasil = {k: v for k, v in db_lab_results.items()
             if v.get("subject", {}).get("reference") == f"Patient/{patient_id}"}
    return {"patient_id": patient_id, "results": list(hasil.values())}

# ============================================================
# [INTEGRASI] Kirim Resep ke Apotek (K4)
# ============================================================
@app.post("/kirim-resep/{med_id}", tags=["Integrasi"])
def kirim_resep_ke_apotek(med_id: str):
    """
    Mengirim resep yang sudah dibuat ke Apotek.
    """
    if med_id not in db_meds:
        raise HTTPException(status_code=404,
            detail=f"Resep '{med_id}' tidak ditemukan")

    m = db_meds[med_id]
    fhir_payload = {
        "resourceType": "MedicationRequest",
        "id": med_id,
        "status": "active",
        "intent": "order",
        "medicationCodeableConcept": {"text": m.nama_obat},
        "subject": {"reference": f"Patient/{m.patient_id}"},
        "requester": {"reference": f"Practitioner/{m.prescriber}"},
        "dosageInstruction": [{
            "text": f"{m.frekuensi}, {m.dosis}, rute {m.rute}",
            "timing": {"repeat": {"frequency": 1, "period": 1,
                                  "periodUnit": "d"}}
        }],
        "dispenseRequest": {
            "quantity": {"value": m.durasi_hari, "unit": "tablet"},
            "expectedSupplyDuration": {
                "value": m.durasi_hari, "unit": "d"
            }
        }
    }

    try:
        resp = requests.post(f"{K4_URL}/fhir/MedicationRequest",
                             json=fhir_payload, timeout=10)
        resp.raise_for_status()
        m.status = "sent_to_pharmacy"
        return {"status": "resep_dikirim", "apotek_resp": resp.json()}
    except Exception as e:
        return {"status": "gagal", "detail": str(e)}

# ============================================================
# [TERIMA] Konfirmasi Dispense dari Apotek (K4)
# ============================================================
@app.post("/fhir/MedicationDispense", tags=["Integrasi"])
def terima_konfirmasi_dispense(dispense: IncomingDispense):
    db_dispense[dispense.id] = dispense.dict()
    return {"status": "received", "dispense_id": dispense.id}

# ============================================================
# [INTEGRASI] Laporan ke Dinkes (K5)
# ============================================================
@app.post("/laporan-kasus", tags=["Integrasi"])
def laporan_ke_dinkes(patient_id: str, condition_id: str):
    if patient_id not in db_pasien:
        raise HTTPException(status_code=404, detail="Pasien tidak ditemukan")
    pasien = db_pasien[patient_id]
    kondisi = db_kondisi.get(condition_id)
    usia = (date.today() - pasien.tanggal_lahir).days // 365
    payload = {
        "sumber": "rsup-sardjito",
        "jenis_laporan": "kasus_baru",
        "tanggal": str(date.today()),
        "pasien_id": patient_id,
        "usia": usia,
        "jenis_kelamin": pasien.jenis_kelamin,
        "diagnosis_icd10": kondisi.icd10_code if kondisi else "Z99",
        "diagnosis_display": kondisi.display if kondisi else "",
        "kecamatan": "Depok", "kabupaten": "Sleman",
        "rawat_inap": True
    }
    try:
        resp = requests.post(f"{K5_URL}/api/laporan-kasus",
                             json=payload, timeout=10)
        resp.raise_for_status()
        return {"status": "terkirim"}
    except Exception as e:
        return {"status": "gagal", "detail": str(e)}
