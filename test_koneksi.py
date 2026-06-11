import requests
from config import K1_URL, K2_URL, K3_URL, K4_URL, K5_URL

SYSTEMS = {
    "K1 Puskesmas": K1_URL,
    "K2 Rumah Sakit": K2_URL,
    "K3 Laboratorium": K3_URL,
    "K4 Apotek": K4_URL,
    "K5 Dinas Kesehatan": K5_URL,
}

print("Menguji koneksi ke semua sistem...\n")
for nama, url in SYSTEMS.items():
    try:
        r = requests.get(f"{url}/", timeout=60)  # timeout besar untuk cold start
        if r.status_code == 200:
            print(f"[OK]  {nama}: {url}")
        else:
            print(f"[!!]  {nama}: status {r.status_code}")
    except requests.exceptions.ConnectionError:
        print(f"[ERR] {nama}: tidak dapat dijangkau ({url})")
    except requests.exceptions.Timeout:
        print(f"[TO]  {nama}: timeout - mungkin sedang cold start, coba lagi")
