"""
VAŞAK ERP v15.0 · Maviş 🐱
FastAPI Backend — Render.com
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import os, jwt, httpx, json

# ─── Ayarlar ────────────────────────────────────────────────────────────────
SUPABASE_URL  = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY  = os.getenv("SUPABASE_KEY", "")
JWT_SECRET    = os.getenv("JWT_SECRET", "vasak_gizli_anahtar_2025")
SIFRE         = os.getenv("VASAK_SIFRE", "123456")
JWT_EXP_SAAT  = 24

app = FastAPI(
    title="VAŞAK ERP API",
    description="v15.0 Maviş — Et & Tavuk Stok Takip Sistemi",
    version="15.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# ─── Supabase yardımcıları ──────────────────────────────────────────────────
HEADERS = lambda: {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

async def sb_get(tablo: str, params: str = ""):
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{SUPABASE_URL}/rest/v1/{tablo}?{params}", headers=HEADERS())
        r.raise_for_status()
        return r.json()

async def sb_post(tablo: str, veri: dict):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{SUPABASE_URL}/rest/v1/{tablo}", headers=HEADERS(), json=veri)
        r.raise_for_status()
        return r.json()

async def sb_patch(tablo: str, id: int, veri: dict):
    async with httpx.AsyncClient() as c:
        r = await c.patch(
            f"{SUPABASE_URL}/rest/v1/{tablo}?id=eq.{id}",
            headers=HEADERS(), json=veri
        )
        r.raise_for_status()
        return r.json()

async def sb_delete(tablo: str, id: int):
    async with httpx.AsyncClient() as c:
        r = await c.delete(f"{SUPABASE_URL}/rest/v1/{tablo}?id=eq.{id}", headers=HEADERS())
        r.raise_for_status()
        return {"silindi": True}

# ─── JWT ────────────────────────────────────────────────────────────────────
def token_olustur():
    exp = datetime.utcnow() + timedelta(hours=JWT_EXP_SAAT)
    return jwt.encode({"sub": "vasak_kullanici", "exp": exp}, JWT_SECRET, algorithm="HS256")

def token_dogrula(cred: HTTPAuthorizationCredentials = Depends(security)):
    try:
        jwt.decode(cred.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token süresi doldu")
    except Exception:
        raise HTTPException(status_code=401, detail="Geçersiz token")
    return cred.credentials

# ─── Modeller ───────────────────────────────────────────────────────────────
class GirisIstegi(BaseModel):
    sifre: str

class UrunEkle(BaseModel):
    ad: str
    barkod: Optional[str] = None
    kategori: str = "küvet"          # küvet | takoz
    fiyat: float = 0.0
    stok: float = 0.0
    birim: str = "kg"
    aciklama: Optional[str] = None

class UrunGuncelle(BaseModel):
    ad: Optional[str] = None
    barkod: Optional[str] = None
    kategori: Optional[str] = None
    fiyat: Optional[float] = None
    stok: Optional[float] = None
    birim: Optional[str] = None
    aciklama: Optional[str] = None

class StokGuncelle(BaseModel):
    miktar: float
    islem: str = "ekle"              # ekle | cikar | ayarla
    not_: Optional[str] = None

class HareketEkle(BaseModel):
    urun_id: int
    islem_tipi: str                  # giris | cikis | sayim
    miktar: float
    not_: Optional[str] = None

# ─── Auth ────────────────────────────────────────────────────────────────────
@app.post("/giris")
async def giris(istek: GirisIstegi):
    if istek.sifre != SIFRE:
        raise HTTPException(status_code=401, detail="Hatalı şifre")
    return {"token": token_olustur(), "mesaj": "Giriş başarılı 🐱"}

@app.get("/saglik")
async def saglik():
    return {"durum": "çalışıyor", "versiyon": "v15.0 Maviş", "zaman": datetime.now().isoformat()}

# ─── Ürünler ────────────────────────────────────────────────────────────────
@app.get("/urunler")
async def urunleri_listele(
    kategori: Optional[str] = None,
    ara: Optional[str] = None,
    _=Depends(token_dogrula)
):
    params = "order=ad.asc"
    if kategori:
        params += f"&kategori=eq.{kategori}"
    if ara:
        params += f"&ad=ilike.*{ara}*"
    return await sb_get("urunler", params)

@app.get("/urunler/{id}")
async def urun_getir(id: int, _=Depends(token_dogrula)):
    sonuc = await sb_get("urunler", f"id=eq.{id}")
    if not sonuc:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    return sonuc[0]

@app.get("/urunler/barkod/{barkod}")
async def barkodla_getir(barkod: str, _=Depends(token_dogrula)):
    sonuc = await sb_get("urunler", f"barkod=eq.{barkod}")
    if not sonuc:
        raise HTTPException(status_code=404, detail="Barkod bulunamadı")
    return sonuc[0]

@app.post("/urunler", status_code=201)
async def urun_ekle(urun: UrunEkle, _=Depends(token_dogrula)):
    veri = urun.dict()
    veri["guncelleme"] = datetime.now().isoformat()
    return await sb_post("urunler", veri)

@app.patch("/urunler/{id}")
async def urun_guncelle(id: int, guncelleme: UrunGuncelle, _=Depends(token_dogrula)):
    veri = {k: v for k, v in guncelleme.dict().items() if v is not None}
    veri["guncelleme"] = datetime.now().isoformat()
    return await sb_patch("urunler", id, veri)

@app.delete("/urunler/{id}")
async def urun_sil(id: int, _=Depends(token_dogrula)):
    return await sb_delete("urunler", id)

@app.post("/urunler/{id}/stok")
async def stok_guncelle(id: int, istek: StokGuncelle, _=Depends(token_dogrula)):
    urun = await urun_getir(id, _)
    mevcut = urun.get("stok", 0)

    if istek.islem == "ekle":
        yeni = mevcut + istek.miktar
        islem_tipi = "giris"
    elif istek.islem == "cikar":
        yeni = mevcut - istek.miktar
        islem_tipi = "cikis"
    else:  # ayarla
        yeni = istek.miktar
        islem_tipi = "sayim"

    if yeni < 0:
        raise HTTPException(status_code=400, detail=f"Yetersiz stok (mevcut: {mevcut})")

    await sb_patch("urunler", id, {"stok": yeni, "guncelleme": datetime.now().isoformat()})

    # Hareket kaydı
    try:
        await sb_post("hareketler", {
            "urun_id": id,
            "islem_tipi": islem_tipi,
            "miktar": istek.miktar,
            "onceki_stok": mevcut,
            "sonraki_stok": yeni,
            "not_": istek.not_,
            "tarih": datetime.now().isoformat()
        })
    except Exception:
        pass  # Hareket tablosu yoksa sessiz geç

    return {"urun_id": id, "onceki": mevcut, "yeni": yeni, "islem": istek.islem}

# ─── Hareketler ─────────────────────────────────────────────────────────────
@app.get("/hareketler")
async def hareketleri_listele(
    urun_id: Optional[int] = None,
    limit: int = 50,
    _=Depends(token_dogrula)
):
    params = f"order=tarih.desc&limit={limit}"
    if urun_id:
        params += f"&urun_id=eq.{urun_id}"
    return await sb_get("hareketler", params)

# ─── Analiz ─────────────────────────────────────────────────────────────────
@app.get("/analiz")
async def analiz(_=Depends(token_dogrula)):
    try:
        urunler = await sb_get("urunler", "order=stok.asc")
        toplam_urun = len(urunler)
        toplam_stok = sum(u.get("stok", 0) for u in urunler)
        toplam_deger = sum(u.get("stok", 0) * u.get("fiyat", 0) for u in urunler)
        kritik = [u for u in urunler if u.get("stok", 0) < 10]
        kuvet_sayisi = sum(1 for u in urunler if u.get("kategori") == "küvet")
        takoz_sayisi = sum(1 for u in urunler if u.get("kategori") == "takoz")

        return {
            "toplam_urun": toplam_urun,
            "toplam_stok_kg": round(toplam_stok, 2),
            "toplam_deger_tl": round(toplam_deger, 2),
            "kritik_stok_sayisi": len(kritik),
            "kritik_urunler": kritik[:5],
            "kuvet_sayisi": kuvet_sayisi,
            "takoz_sayisi": takoz_sayisi,
            "son_guncelleme": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── Supabase tablo oluşturma SQL (bilgi amaçlı) ──────────────────────────
@app.get("/kurulum-sql", include_in_schema=False)
async def kurulum_sql():
    return {
        "urunler": """
CREATE TABLE urunler (
  id SERIAL PRIMARY KEY,
  ad TEXT NOT NULL,
  barkod TEXT UNIQUE,
  kategori TEXT DEFAULT 'küvet',
  fiyat FLOAT DEFAULT 0,
  stok FLOAT DEFAULT 0,
  birim TEXT DEFAULT 'kg',
  aciklama TEXT,
  guncelleme TIMESTAMPTZ DEFAULT NOW()
);""",
        "hareketler": """
CREATE TABLE hareketler (
  id SERIAL PRIMARY KEY,
  urun_id INT REFERENCES urunler(id),
  islem_tipi TEXT,
  miktar FLOAT,
  onceki_stok FLOAT,
  sonraki_stok FLOAT,
  not_ TEXT,
  tarih TIMESTAMPTZ DEFAULT NOW()
);"""
    }
