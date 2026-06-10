// StockFlow v15.0 — Cloudflare Worker + D1

const JWT_SECRET = "vasak_gizli_anahtar_2025";
const VASAK_SIFRE = "123456";

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

async function tkontrol(req) {
  const auth = req.headers.get("Authorization") || "";
  if (!auth.startsWith("Bearer ")) return false;
  return await jwtDogrula(auth.slice(7), JWT_SECRET);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    const method = request.method;
    const DB = env.DB;

    if (method === "OPTIONS") return new Response(null, {
      status: 204,
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
      }
    });

    if (path === "/" || path === "/api/saglik") return json({ sistem: "StockFlow", versiyon: "v15.0", durum: "çalışıyor 🐱" });

    // ── GİRİŞ ──
    if (path === "/api/giris" && method === "POST") {
      try {
        const body = await request.json();
        if (body.sifre !== VASAK_SIFRE) return hata("Hatalı şifre!", 401);
        const exp = Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 30;
        const token = await jwtImzala({ sub: "vasak", exp }, JWT_SECRET);
        return json({ token });
      } catch (e) { return hata("Giriş hatası: " + e.message, 500); }
    }

    if (!(await tkontrol(request))) return hata("Geçersiz token", 401);

    // ── ÜRÜNLER ──
    if (path === "/api/urunler") {
      if (method === "GET") {
        try {
          const { results } = await DB.prepare("SELECT * FROM urunler ORDER BY id DESC").all();
          return json({ urunler: results, toplam: results.length });
        } catch (e) { return hata("DB hatası: " + e.message, 500); }
      }

      if (method === "POST") {
        try {
          const u = await request.json();
          await DB.prepare(`
            INSERT INTO urunler (barkod, kategori, gelis_tarihi, ilk_miktar, kalan_miktar)
            VALUES (?, ?, ?, ?, ?)
          `).bind(
            u.barkod, u.kategori, u.gelis_tarihi || "-",
            u.ilk_miktar || 0, u.kalan_miktar ?? u.ilk_miktar ?? 0
          ).run();
          return json({ ok: true });
        } catch (e) {
          if (e.message.includes("UNIQUE")) return hata("Bu barkod zaten kayıtlı!", 409);
          return hata("DB hatası: " + e.message, 500);
        }
      }
    }

    // ── ÜRÜN GÜNCELLE / SİL ──
    const m = path.match(/^\/api\/urunler\/(\d+)$/);
    if (m) {
      const id = parseInt(m[1]);

      if (method === "PUT") {
        try {
          const g = await request.json();
          const izinli = [
            "barkod","gelis_tarihi","kullanim_tarihi","tekrar_kullanim_tarihi",
            "kuvet_kullanim_tarihi","kuvet_miktar",
            "takoz_kullanim_tarihi","takoz_miktar",
            "takoz2_kullanim_tarihi","takoz2_miktar",
            "kalan_miktar","tekrar_miktar","zayi_miktar","zayi_tarihi",
            "transfer_miktar","transfer_tarihi","transfer_yon","transfer_isletme"
          ];
          const alanlar = Object.entries(g).filter(([k, v]) => izinli.includes(k) && v !== null && v !== undefined);
          if (!alanlar.length) return hata("Güncellenecek alan yok", 400);
          const set = alanlar.map(([k]) => `${k} = ?`).join(", ");
          const degerler = alanlar.map(([, v]) => v);
          await DB.prepare(`UPDATE urunler SET ${set} WHERE id = ?`).bind(...degerler, id).run();
          return json({ ok: true });
        } catch (e) { return hata("DB hatası: " + e.message, 500); }
      }

      if (method === "DELETE") {
        try {
          await DB.prepare("DELETE FROM urunler WHERE id = ?").bind(id).run();
          return json({ ok: true });
        } catch (e) { return hata("DB hatası: " + e.message, 500); }
      }
    }

    // ── ANALİZ ──
    if (path === "/api/analiz" && method === "GET") {
      try {
        const { results } = await DB.prepare("SELECT * FROM urunler").all();
        const bugun = new Date();
        const s7 = { Et: 0, Tavuk: 0 }, s30 = { Et: 0, Tavuk: 0 };
        for (const u of results) {
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
      } catch (e) { return hata("DB hatası: " + e.message, 500); }
    }

    return hata("Endpoint bulunamadı", 404);
  },
};
