// VAŞAK ERP v15.0 Maviş — Cloudflare Worker

async function jwtImzala(payload, secret) {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" })).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  const body = btoa(JSON.stringify(payload)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  const veri = `${header}.${body}`;
  const anahtar = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const imza = await crypto.subtle.sign("HMAC", anahtar, new TextEncoder().encode(veri));
  const imzaB64 = btoa(String.fromCharCode(...new Uint8Array(imza))).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  return `${veri}.${imzaB64}`;
}

async function jwtDogrula(token, secret) {
  try {
    const p = token.split(".");
    if (p.length !== 3) return false;
    const veri = `${p[0]}.${p[1]}`;
    const anahtar = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["verify"]);
    const imzaBytes = Uint8Array.from(atob(p[2].replace(/-/g, "+").replace(/_/g, "/")), c => c.charCodeAt(0));
    const gecerli = await crypto.subtle.verify("HMAC", anahtar, imzaBytes, new TextEncoder().encode(veri));
    if (!gecerli) return false;
    const payload = JSON.parse(atob(p[1].replace(/-/g, "+").replace(/_/g, "/")));
    if (payload.exp && Date.now() / 1000 > payload.exp) return false;
    return true;
  } catch { return false; }
}

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

function hata(mesaj, status = 400) { return json({ detail: mesaj }, status); }
function g(env, key, fb = "") { return (env && env[key]) ? env[key] : fb; }
function sbH(env) {
  const k = g(env, "SUPABASE_KEY");
  return { "apikey": k, "Authorization": `Bearer ${k}`, "Content-Type": "application/json", "Prefer": "return=representation" };
}

function iso2dmy(iso) {
  if (!iso || iso === "-") return "-";
  try { const [y, m, d] = iso.split("-"); return `${d}.${m}.${y}`; } catch { return iso; }
}

function tarihlerDmy(u) {
  for (const a of ["gelis_tarihi","kullanim_tarihi","tekrar_kullanim_tarihi","kuvet_kullanim_tarihi","takoz_kullanim_tarihi","zayi_tarihi","transfer_tarihi"]) {
    if (u[a] && typeof u[a] === "string" && u[a].length === 10 && u[a][4] === "-") u[a] = iso2dmy(u[a]);
  }
  return u;
}

async function tkontrol(req, env) {
  const auth = req.headers.get("Authorization") || "";
  if (!auth.startsWith("Bearer ")) return false;
  return await jwtDogrula(auth.slice(7), g(env, "JWT_SECRET", "vasak_gizli_anahtar_2025"));
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;

    if (method === "OPTIONS") return new Response(null, { status: 204, headers: { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS", "Access-Control-Allow-Headers": "Content-Type, Authorization" } });

    if (path === "/" || path === "/api/saglik") return json({ sistem: "VAŞAK ERP", versiyon: "v15.0 Maviş", durum: "çalışıyor 🐱" });

    if (path === "/api/giris" && method === "POST") {
      try {
        const body = await request.json();
        if (body.sifre !== g(env, "VASAK_SIFRE", "123456")) return hata("Hatalı şifre!", 401);
        const exp = Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 30;
        const token = await jwtImzala({ sub: "vasak", exp }, g(env, "JWT_SECRET", "vasak_gizli_anahtar_2025"));
        return json({ token });
      } catch (e) { return hata("Giriş hatası: " + e.message, 500); }
    }

    if (!(await tkontrol(request, env))) return hata("Geçersiz token", 401);

    const sbUrl = g(env, "SUPABASE_URL");

    if (path === "/api/urunler") {
      if (method === "GET") {
        try {
          const r = await fetch(`${sbUrl}/rest/v1/urunler?select=*&order=id.desc`, { headers: sbH(env) });
          if (!r.ok) return hata("Supabase: " + await r.text(), 500);
          const liste = (await r.json()).map(tarihlerDmy);
          return json({ urunler: liste, toplam: liste.length });
        } catch (e) { return hata("Hata: " + e.message, 500); }
      }
      if (method === "POST") {
        try {
          const u = await request.json();
          const veri = { barkod: u.barkod, kategori: u.kategori, gelis_tarihi: u.gelis_tarihi || "-", ilk_miktar: u.ilk_miktar || 0, kalan_miktar: u.kalan_miktar ?? u.ilk_miktar ?? 0 };
          const r = await fetch(`${sbUrl}/rest/v1/urunler`, { method: "POST", headers: sbH(env), body: JSON.stringify(veri) });
          if (![200, 201].includes(r.status)) return hata("Supabase: " + await r.text(), 500);
          return json({ ok: true });
        } catch (e) { return hata("Hata: " + e.message, 500); }
      }
    }

    const m = path.match(/^\/api\/urunler\/(\d+)$/);
    if (m) {
      const id = m[1];
      if (method === "PUT") {
        try {
          const g2 = await request.json();
          const veri = Object.fromEntries(Object.entries(g2).filter(([, v]) => v !== null && v !== undefined));
          if (!Object.keys(veri).length) return hata("Güncellenecek alan yok", 400);
          const r = await fetch(`${sbUrl}/rest/v1/urunler?id=eq.${id}`, { method: "PATCH", headers: sbH(env), body: JSON.stringify(veri) });
          if (![200, 204].includes(r.status)) return hata("Supabase: " + await r.text(), 500);
          return json({ ok: true });
        } catch (e) { return hata("Hata: " + e.message, 500); }
      }
      if (method === "DELETE") {
        try {
          const r = await fetch(`${sbUrl}/rest/v1/urunler?id=eq.${id}`, { method: "DELETE", headers: sbH(env) });
          if (![200, 204].includes(r.status)) return hata("Supabase: " + await r.text(), 500);
          return json({ ok: true });
        } catch (e) { return hata("Hata: " + e.message, 500); }
      }
    }

    if (path === "/api/analiz" && method === "GET") {
      try {
        const r = await fetch(`${sbUrl}/rest/v1/urunler?select=*`, { headers: sbH(env) });
        if (!r.ok) return hata("Supabase hatası", 500);
        const urunler = (await r.json()).map(tarihlerDmy);
        const bugun = new Date();
        const s7 = { Et: 0, Tavuk: 0 }, s30 = { Et: 0, Tavuk: 0 };
        for (const u of urunler) {
          const kat = u.kategori;
          if (!["Et", "Tavuk"].includes(kat)) continue;
          const tuk = Math.max(0, (u.ilk_miktar || 0) - (u.kalan_miktar || 0) - (u.zayi_miktar || 0));
          if (tuk <= 0) continue;
          const tarStr = u.kullanim_tarihi || "-";
          if (tarStr && tarStr !== "-") {
            try {
              const [d, mo, y] = tarStr.split(".");
              const tar = new Date(+y, mo - 1, +d);
              const fark = Math.floor((bugun - tar) / 86400000);
              if (fark <= 7) s7[kat] += tuk;
              if (fark <= 30) s30[kat] += tuk;
            } catch { }
          }
        }
        return json({ son_7_gun: s7, son_30_gun: s30 });
      } catch (e) { return hata("Hata: " + e.message, 500); }
    }

    return hata("Endpoint bulunamadı", 404);
  },
};
