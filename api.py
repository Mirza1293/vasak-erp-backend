from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Optional
import os, jwt, httpx
from datetime import datetime, timedelta

app = FastAPI(title="VAŞAK ERP v15.0 Maviş")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
JWT_SECRET   = os.environ.get("JWT_SECRET", "vasak_gizli_anahtar_2025")
VASAK_SIFRE  = os.environ.get("VASAK_SIFRE", "123456")

security = HTTPBearer()

def sb_headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json", "Prefer": "return=representation"}

async def token_kontrol(cred: HTTPAuthorizationCredentials = Depends(security)):
    try:
        jwt.decode(cred.credentials, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=401, detail="Geçersiz token")

def iso2dmy(iso: str) -> str:
    if not iso or iso == "-":
        return "-"
    try:
        y, m, d = iso.split("-")
        return f"{d}.{m}.{y}"
    except Exception:
        return iso

def supabase_tarihleri_dmy(u: dict) -> dict:
    for alan in ["gelis_tarihi", "kullanim_tarihi", "tekrar_kullanim_tarihi",
                 "kuvet_kullanim_tarihi", "takoz_kullanim_tarihi", "zayi_tarihi"]:
        if alan in u and u[alan]:
            val = u[alan]
            if isinstance(val, str) and len(val) == 10 and val[4] == "-":
                u[alan] = iso2dmy(val)
    return u

# ── GİRİŞ ──────────────────────────────────────────────────────────────────────

class GirisIstek(BaseModel):
    sifre: str

@app.post("/api/giris")
async def giris(istek: GirisIstek):
    if istek.sifre != VASAK_SIFRE:
        raise HTTPException(status_code=401, detail="Hatalı şifre!")
    token = jwt.encode(
        {"sub": "vasak", "exp": datetime.utcnow() + timedelta(days=30)},
        JWT_SECRET, algorithm="HS256"
    )
    return {"token": token}

# ── ÜRÜNLER ────────────────────────────────────────────────────────────────────

@app.get("/api/urunler")
async def urunler_listele(_=Depends(token_kontrol)):
    async with httpx.AsyncClient() as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/urunler?select=*&order=id.desc",
            headers=sb_headers()
        )
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Supabase hatası")
    liste = [supabase_tarihleri_dmy(u) for u in r.json()]
    return {"urunler": liste, "toplam": len(liste)}

class UrunEkle(BaseModel):
    barkod: str
    kategori: str
    gelis_tarihi: Optional[str] = None
    ilk_miktar: Optional[float] = None
    kalan_miktar: Optional[float] = None

@app.post("/api/urunler")
async def urun_ekle(u: UrunEkle, _=Depends(token_kontrol)):
    veri = {
        "barkod": u.barkod,
        "kategori": u.kategori,
        "gelis_tarihi": u.gelis_tarihi or "-",
        "ilk_miktar": u.ilk_miktar or 0,
        "kalan_miktar": u.kalan_miktar if u.kalan_miktar is not None else (u.ilk_miktar or 0),
    }
    async with httpx.AsyncClient() as c:
        r = await c.post(
            f"{SUPABASE_URL}/rest/v1/urunler",
            headers=sb_headers(), json=veri
        )
    if r.status_code not in (200, 201):
        raise HTTPException(status_code=500, detail=f"Supabase: {r.text}")
    return {"ok": True}

class UrunGuncelle(BaseModel):
    kullanim_tarihi: Optional[str] = None
    tekrar_kullanim_tarihi: Optional[str] = None
    kuvet_kullanim_tarihi: Optional[str] = None
    takoz_kullanim_tarihi: Optional[str] = None
    kalan_miktar: Optional[float] = None
    tekrar_miktar: Optional[float] = None
    kuvet_miktar: Optional[float] = None
    takoz_miktar: Optional[float] = None
    zayi_miktar: Optional[float] = None
    zayi_tarihi: Optional[str] = None
    barkod: Optional[str] = None
    gelis_tarihi: Optional[str] = None

@app.put("/api/urunler/{urun_id}")
async def urun_guncelle(urun_id: int, g: UrunGuncelle, _=Depends(token_kontrol)):
    veri = {k: v for k, v in g.dict().items() if v is not None}
    if not veri:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")
    async with httpx.AsyncClient() as c:
        r = await c.patch(
            f"{SUPABASE_URL}/rest/v1/urunler?id=eq.{urun_id}",
            headers=sb_headers(), json=veri
        )
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=500, detail=f"Supabase: {r.text}")
    return {"ok": True}

@app.delete("/api/urunler/{urun_id}")
async def urun_sil(urun_id: int, _=Depends(token_kontrol)):
    async with httpx.AsyncClient() as c:
        r = await c.delete(
            f"{SUPABASE_URL}/rest/v1/urunler?id=eq.{urun_id}",
            headers=sb_headers()
        )
    if r.status_code not in (200, 204):
        raise HTTPException(status_code=500, detail=f"Supabase: {r.text}")
    return {"ok": True}

# ── ANALİZ ─────────────────────────────────────────────────────────────────────

@app.get("/api/analiz")
async def analiz(_=Depends(token_kontrol)):
    async with httpx.AsyncClient() as c:
        r = await c.get(
            f"{SUPABASE_URL}/rest/v1/urunler?select=*",
            headers=sb_headers()
        )
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail="Supabase hatası")

    urunler = [supabase_tarihleri_dmy(u) for u in r.json()]
    bugun = datetime.now()
    s7  = {"Et": 0.0, "Tavuk": 0.0}
    s30 = {"Et": 0.0, "Tavuk": 0.0}

    for u in urunler:
        kat = u.get("kategori", "")
        if kat not in ("Et", "Tavuk"):
            continue
        ilk = u.get("ilk_miktar") or 0
        kal = u.get("kalan_miktar") or 0
        zayi = u.get("zayi_miktar") or 0
        tuk = max(0, ilk - kal - zayi)
        if tuk <= 0:
            continue
        tar_str = u.get("kullanim_tarihi") or "-"
        if tar_str and tar_str != "-":
            try:
                d, m, y = tar_str.split(".")
                tar = datetime(int(y), int(m), int(d))
                fark = (bugun - tar).days
                if fark <= 7:
                    s7[kat] += tuk
                if fark <= 30:
                    s30[kat] += tuk
            except Exception:
                pass

    return {"son_7_gun": s7, "son_30_gun": s30}

# ── SAĞLIK ─────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"sistem": "VAŞAK ERP", "versiyon": "v15.0 Maviş", "durum": "çalışıyor 🐱"}

@app.get("/api/saglik")
async def saglik():
    return {"durum": "ok"}
