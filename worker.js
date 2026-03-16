// VAŞAK ERP v15.0 Maviş — Cloudflare Worker
// Environment variables: SUPABASE_URL, SUPABASE_KEY, JWT_SECRET, VASAK_SIFRE

// ── JWT (HS256) ──────────────────────────────────────────────────────────────

async function jwtImzala(payload, secret) {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" })).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  const body = btoa(JSON.stringify(payload)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  const veri = `${header}.${body}`;
  const anahtar = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  const imza = await crypto.subtle.sign("HMAC", anahtar, new TextEncoder().encode(veri));
  const imzaB64 = btoa(String.fromCharCode(...new Uint8Array(imza))).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  return `${veri}.${imzaB64}`;
}

async function jwtDogrula(token, secret) {
  const parcalar = token.split(".");
  if (parcalar.length !== 3) return false;
  const veri = `${parcalar[0]}.${parcalar[1]}`;
  const anahtar = await crypto.subtle.importKey(
    "raw", new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" }, false, ["verify"]
  );
  const imzaBytes = Uint8Array.from(atob(parcalar[2].replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
  const gecerli = await crypto.subtle.verify("HMAC", anahtar, imzaBytes, new TextEncoder().encode(veri));
  if (!gecerli) return false;
  const payload = JSON.parse(atob(parcalar[1].replace(/-/g, "+").replace(/_/g, "/")));
  if (payload.exp && Date.now() / 1000 > payload.exp) return false;
  return true;
}

// ── YARDIMCILAR ─────────────────────────────────────────────────────────────

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
    },
  });
}

function hata(mesaj, status = 400) {
  return json({ detail: mesaj }, status);
}

function sbHeaders(env) {
  return {
    "apikey": env.SUPABASE_KEY,
    "Authorization": `Bearer ${env.SUPABASE_KEY}`,
    "Content-Type": "application/json",
    "Prefer": "return=representation",
  };
}

function iso2dmy(iso) {
  if (!iso || iso === "-") return "-";
  try {
    const [y, m, d] = iso.split("-");
    return `${d}.${m}.${y}`;
  } catch { return iso; }
}

function tarihlerDmy(u) {
  const alanlar = ["gelis_tarihi", "kullanim_tarihi", "tekrar_kullanim_tarihi",
    "kuvet_kullanim_tarihi", "takoz_kullanim_tarihi", "zayi_tarihi", "transfer_tarihi"];
  for (const alan of alanlar) {
    if (u[alan] && typeof u[alan] === "string" && u[alan].length === 10 && u[alan][4] === "-") {
      u[alan] = iso2dmy(u[alan]);
    }
  }
  return u;
}

async function tokenKontrol(request, env) {
  const auth = request.headers.get("Authorization") || "";
  if (!auth.startsWith("Bearer ")) return false;
  return await jwtDogrula(auth.slice(7), env.JWT_SECRET);
}

// ── HANDLER ─────────────────────────────────────────────────────────────────

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    // CORS preflight
    if (method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, Authorization",
        },
      });
    }

    // ── SAĞLIK ──
    if (path === "/" || path === "/api/saglik") {
      return json({ sistem: "VAŞAK ERP", versiyon: "v15.0 Maviş", durum: "çalışıyor 🐱" });
    }

    // ── GİRİŞ ──
    if (path === "/api/giris" && method === "POST") {
      const body = await request.json();
      if (body.sifre !== env.VASAK_SIFRE) return hata("Hatalı şifre!", 401);
      const exp = Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 30;
      const token = await jwtImzala({ sub: "vasak", exp }, env.JWT_SECRET);
      return json({ token });
    }

    // Token kontrolü (diğer tüm endpointler)
    if (!(await tokenKontrol(request, env))) return hata("Geçersiz token", 401);

    // ── ÜRÜNLER LİSTE / EKLE ──
    if (path === "/api/urunler") {
      if (method === "GET") {
        const r = await fetch(`${env.SUPABASE_URL}/rest/v1/urunler?select=*&order=id.desc`, {
          headers: sbHeaders(env),
        });
        if (!r.ok) return hata("Supabase hatası", 500);
        const liste = (await r.json()).map(tarihlerDmy);
        return json({ urunler: liste, toplam: liste.length });
      }

      if (method === "POST") {
        const u = await request.json();
        const veri = {
          barkod: u.barkod,
          kategori: u.kategori,
          gelis_tarihi: u.gelis_tarihi || "-",
          ilk_miktar: u.ilk_miktar || 0,
          kalan_miktar: u.kalan_miktar ?? u.ilk_miktar ?? 0,
        };
        const r = await fetch(`${env.SUPABASE_URL}/rest/v1/urunler`, {
          method: "POST",
          headers: sbHeaders(env),
          body: JSON.stringify(veri),
        });
        if (![200, 201].includes(r.status)) return hata(`Supabase: ${await r.text()}`, 500);
        return json({ ok: true });
      }
    }

    // ── ÜRÜN GÜNCELLE / SİL ──
    const guncelleMatch = path.match(/^\/api\/urunler\/(\d+)$/);
    if (guncelleMatch) {
      const id = guncelleMatch[1];

      if (method === "PUT") {
        const g = await request.json();
        const veri = Object.fromEntries(Object.entries(g).filter(([, v]) => v !== null && v !== undefined));
        if (!Object.keys(veri).length) return hata("Güncellenecek alan yok", 400);
        const r = await fetch(`${env.SUPABASE_URL}/rest/v1/urunler?id=eq.${id}`, {
          method: "PATCH",
          headers: sbHeaders(env),
          body: JSON.stringify(veri),
        });
        if (![200, 204].includes(r.status)) return hata(`Supabase: ${await r.text()}`, 500);
        return json({ ok: true });
      }

      if (method === "DELETE") {
        const r = await fetch(`${env.SUPABASE_URL}/rest/v1/urunler?id=eq.${id}`, {
          method: "DELETE",
          headers: sbHeaders(env),
        });
        if (![200, 204].includes(r.status)) return hata(`Supabase: ${await r.text()}`, 500);
        return json({ ok: true });
      }
    }

    // ── ANALİZ ──
    if (path === "/api/analiz" && method === "GET") {
      const r = await fetch(`${env.SUPABASE_URL}/rest/v1/urunler?select=*`, {
        headers: sbHeaders(env),
      });
      if (!r.ok) return hata("Supabase hatası", 500);
      const urunler = (await r.json()).map(tarihlerDmy);
      const bugun = new Date();
      const s7 = { Et: 0, Tavuk: 0 };
      const s30 = { Et: 0, Tavuk: 0 };

      for (const u of urunler) {
        const kat = u.kategori;
        if (!["Et", "Tavuk"].includes(kat)) continue;
        const ilk = u.ilk_miktar || 0;
        const kal = u.kalan_miktar || 0;
        const zayi = u.zayi_miktar || 0;
        const tuk = Math.max(0, ilk - kal - zayi);
        if (tuk <= 0) continue;
        const tarStr = u.kullanim_tarihi || "-";
        if (tarStr && tarStr !== "-") {
          try {
            const [d, m, y] = tarStr.split(".");
            const tar = new Date(+y, m - 1, +d);
            const fark = Math.floor((bugun - tar) / 86400000);
            if (fark <= 7) s7[kat] += tuk;
            if (fark <= 30) s30[kat] += tuk;
          } catch { }
        }
      }
      return json({ son_7_gun: s7, son_30_gun: s30 });
    }

    return hata("Endpoint bulunamadı", 404);
  },
};
