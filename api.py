"""
VAŞAK ERP v15.0 · Maviş 🐱
FastAPI Backend — Render.com
Supabase şeması: lot/parti bazlı et & tavuk takip
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import os, jwt, httpx

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
JWT_SECRET   = os.getenv("JWT_SECRET", "vasak_gizli_anahtar_2025")
SIFRE        = os.getenv("VASAK_SIFRE", "123456")

app = FastAPI(title="VAŞAK ERP API", description="v15.0 Maviş — Et & Tavuk Lot Takip", version="15.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
security = HTTPBearer()

def headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

async def sb_get(tablo, params=""):
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{SUPABASE_URL}/rest/v1/{tablo}?{params}", headers=headers())
        r.raise_for_status()
        return r.json()

async def sb_post(tablo, veri):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{SUPABASE_URL}/rest/v1/{tablo}", headers=headers(), json=veri)
        r.raise_for_status()
        return r.json()

async def sb_patch(tablo, id, veri):
    async with httpx.AsyncClient() as c:
        r = await c.patch(f"{SUPABASE_URL}/rest/v1/{tablo}?id=eq.{id}", headers=headers(), json=veri)
        r.raise_for_status()
        return r.json()

async def sb_delete(tablo, id):
    async with httpx.AsyncClient() as c:
        r = await c.delete(f"{SUPABASE_URL}/rest/v1/{tablo}?id=eq.{id}", headers=headers())
        r.raise_for_status()
        return {"silindi": True}

def token_olustur():
    exp = datetime.utcnow() + timedelta(hours=24)
    return jwt.encode({"sub": "vasak", "exp": exp}, JWT_SECRET, algorithm="HS256")

def token_dogrula(cred: HTTPAuthorizationCredentials = Depends(security)):
    try:
        jwt.decode(cred.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token süresi doldu")
    except Exception:
        raise HTTPException(status_code=401, detail="Geçersiz token")
    return cred.credentials

class GirisIstegi(BaseModel):
    sifre: str

class LotEkle(BaseModel):
    barkod: Optional[str] = None
    kategori: str = "küvet"
    gelis_tarihi: Optional[str] = None
    ilk_miktar: float = 0.0
    kalan_miktar: Optional[float] = None
    kuvet_miktar: float = 0.0
    takoz_miktar: float = 0.0
    kuvet_kullanim_tarihi: Optional[str] = None
    takoz_kullanim_tarihi: Optional[str] = None
    kullanim_tarihi: Optional[str] = None
    tekrar_kullanim_tarihi: Optional[str] = None
    tekrar_miktar: float = 0.0

class LotGuncelle(BaseModel):
    barkod: Optional[str] = None
    kategori: Optional[str] = None
    gelis_tarihi: Optional[str] = None
    ilk_miktar: Optional[float] = None
    kalan_miktar: Optional[float] = None
    kuvet_miktar: Optional[float] = None
    takoz_miktar: Optional[float] = None
    kuvet_kullanim_tarihi: Optional[str] = None
    takoz_kullanim_tarihi: Optional[str] = None
    kullanim_tarihi: Optional[str] = None
    tekrar_kullanim_tarihi: Optional[str] = None
    tekrar_miktar: Optional[float] = None

class KalanGuncelle(BaseModel):
    miktar: float
    islem: str = "ayarla"   # ekle | cikar | ayarla
    not_: Optional[str] = None

@app.get("/")
async def root():
    return {"uygulama": "VAŞAK ERP", "versiyon": "v15.0 Maviş", "durum": "çalışıyor 🐾", "docs": "/docs"}

@app.get("/saglik")
async def saglik():
    return {"durum": "çalışıyor", "versiyon": "v15.0 Maviş", "zaman": datetime.now().isoformat()}

@app.post("/giris")
async def giris(istek: GirisIstegi):
    if istek.sifre != SIFRE:
        raise HTTPException(status_code=401, detail="Hatalı şifre")
    return {"token": token_olustur(), "mesaj": "Giriş başarılı 🐱"}

@app.get("/urunler")
async def lotlari_listele(kategori: Optional[str] = None, ara: Optional[str] = None, _=Depends(token_dogrula)):
    params = "order=id.desc"
    if kategori:
        params += f"&kategori=eq.{kategori}"
    if ara:
        params += f"&barkod=ilike.*{ara}*"
    return await sb_get("urunler", params)

@app.get("/urunler/{id}")
async def lot_getir(id: int, _=Depends(token_dogrula)):
    sonuc = await sb_get("urunler", f"id=eq.{id}")
    if not sonuc:
        raise HTTPException(status_code=404, detail="Lot bulunamadı")
    return sonuc[0]

@app.get("/urunler/barkod/{barkod}")
async def barkodla_getir(barkod: str, _=Depends(token_dogrula)):
    sonuc = await sb_get("urunler", f"barkod=eq.{barkod}")
    if not sonuc:
        raise HTTPException(status_code=404, detail="Barkod bulunamadı")
    return sonuc[0]

@app.post("/urunler", status_code=201)
async def lot_ekle(lot: LotEkle, _=Depends(token_dogrula)):
    veri = lot.dict()
    if veri["kalan_miktar"] is None:
        veri["kalan_miktar"] = veri["ilk_miktar"]
    if not veri["gelis_tarihi"]:
        veri["gelis_tarihi"] = datetime.now().strftime("%Y-%m-%d")
    return await sb_post("urunler", veri)

@app.patch("/urunler/{id}")
async def lot_guncelle(id: int, guncelleme: LotGuncelle, _=Depends(token_dogrula)):
    veri = {k: v for k, v in guncelleme.dict().items() if v is not None}
    return await sb_patch("urunler", id, veri)

@app.delete("/urunler/{id}")
async def lot_sil(id: int, _=Depends(token_dogrula)):
    return await sb_delete("urunler", id)

@app.post("/urunler/{id}/stok")
async def kalan_guncelle(id: int, istek: KalanGuncelle, _=Depends(token_dogrula)):
    lot = await lot_getir(id, _)
    mevcut = lot.get("kalan_miktar") or 0
    if istek.islem == "ekle":
        yeni = mevcut + istek.miktar
    elif istek.islem == "cikar":
        yeni = mevcut - istek.miktar
        if yeni < 0:
            raise HTTPException(status_code=400, detail=f"Yetersiz stok (mevcut: {mevcut})")
    else:
        yeni = istek.miktar
    return await sb_patch("urunler", id, {"kalan_miktar": yeni})

@app.get("/analiz")
async def analiz(_=Depends(token_dogrula)):
    try:
        lotlar = await sb_get("urunler", "order=id.desc")
        toplam_lot    = len(lotlar)
        toplam_kalan  = sum(l.get("kalan_miktar") or 0 for l in lotlar)
        toplam_ilk    = sum(l.get("ilk_miktar") or 0 for l in lotlar)
        toplam_kuvet  = sum(l.get("kuvet_miktar") or 0 for l in lotlar)
        toplam_takoz  = sum(l.get("takoz_miktar") or 0 for l in lotlar)
        kritik = [l for l in lotlar if 0 < (l.get("kalan_miktar") or 0) < 10]
        return {
            "toplam_urun":        toplam_lot,
            "toplam_stok_kg":     round(toplam_kalan, 2),
            "toplam_deger_tl":    round(toplam_ilk, 2),
            "kritik_stok_sayisi": len(kritik),
            "kritik_urunler":     kritik[:5],
            "toplam_kuvet_kg":    round(toplam_kuvet, 2),
            "toplam_takoz_kg":    round(toplam_takoz, 2),
            "son_guncelleme":     datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
