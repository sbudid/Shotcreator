// Shotcreator AI hooks — Cloudflare Pages Functions (serverless).
// Menggantikan server.py untuk endpoint /api/* di Cloudflare Pages.
// Secret yang dibutuhkan (Pages → Settings → Environment Variables → Secret):
//   COMMANDCODE_API_KEY  — key command-code (Bearer) untuk api.commandcode.ai
//
// Routes (catch-all /api/*):
//   GET  /api/health        -> {ok:true}
//   POST /api/hooks         {story}            -> {top_lines[], bot_lines[]}
//   POST /api/hooks-money   {story}            -> {job_id, status:'done', top_lines[], bot_lines[]}
//   POST /api/hooks-vision  {images:[{data_url}]} -> {job_id, status:'done', top_lines[], bot_lines[]}

const API_BASE = "https://api.commandcode.ai/provider/v1";
const HOOK_MODEL = "deepseek/deepseek-v4-flash"; // hook teks
const VISION_MODEL = "google/gemini-3.8-flash"; // hook vision
const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";

const SYSTEM =
  "Kamu penulis hook video vertikal TikTok/Reels berbahasa Indonesia. " +
  "Wajib balas HANYA dengan JSON mentah tanpa penjelasan, tanpa pembuka, tanpa penutup: " +
  '{"top": ["BARIS ATAS 1", "BARIS ATAS 2"], "bottom": ["BARIS BAWAH"]}. ' +
  "Huruf kapital semua, tiap baris maksimal 28 karakter, 1-2 baris per " +
  "bagian, gaya bikin penasaran dan emosional. " +
  "JANGAN mengklaim pengalaman pribadi seperti 'aku pakai' atau 'favoritku'.";

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

function parseHooks(text) {
  let t = (text || "").trim();
  if (t.startsWith("```")) {
    t = t.replace(/^```[a-z]*\n?/i, "").replace(/```\s*$/, "");
  }
  const obj = JSON.parse(t.slice(t.indexOf("{"), t.lastIndexOf("}") + 1));
  const norm = (arr) => {
    const out = [];
    for (const x of arr || []) {
      let s = String(x).trim().toUpperCase();
      if (!s) continue;
      if (s.length > 28) s = s.slice(0, 28).trim();
      out.push(s);
      if (out.length === 2) break;
    }
    return out;
  };
  const top = norm(obj.top);
  const bottom = norm(obj.bottom);
  if (!top.length || !bottom.length) {
    throw new Error("AI tidak mengembalikan hook yang valid");
  }
  return { top_lines: top, bot_lines: bottom };
}

async function chat(model, messages, apiKey) {
  const res = await fetch(API_BASE + "/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + apiKey,
      "User-Agent": UA,
    },
    body: JSON.stringify({ model, messages, temperature: 0.7, max_tokens: 500 }),
  });
  if (!res.ok) {
    const detail = (await res.text()).slice(0, 200);
    throw new Error("AI HTTP " + res.status + ": " + detail);
  }
  const data = await res.json();
  const content = data && data.choices && data.choices[0] &&
    data.choices[0].message && data.choices[0].message.content;
  if (!content) throw new Error("Respons AI tak terduga");
  return { content, usage: data.usage || null }; // DEBUG SEMENTARA
}

function rid(prefix) {
  const h = "0123456789abcdef";
  let s = prefix;
  for (let i = 0; i < 12; i++) s += h[Math.floor(Math.random() * 16)];
  return s;
}

export async function onRequest({ request, env }) {
  const url = new URL(request.url);
  const path = url.pathname;

  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
      },
    });
  }

  try {
    if (path === "/api/health" && request.method === "GET") {
      return json({ ok: true });
    }

    if (path.startsWith("/api/hooks")) {
      const apiKey = (env.COMMANDCODE_API_KEY || "").trim();
      if (!apiKey) {
        return json(
          { error: "AI belum dikonfigurasi (secret COMMANDCODE_API_KEY kosong)." },
          503
        );
      }

      if (path === "/api/hooks" && request.method === "POST") {
        const body = await request.json();
        const story = String(body.story || "").trim();
        if (!story) return json({ error: "Isi dulu deskripsi ceritanya." }, 400);
        const r = await chat(
          HOOK_MODEL,
          [{ role: "user", content: SYSTEM + "\n\nDeskripsi:\n" + story }],
          apiKey
        );
        const out0 = parseHooks(r.content);
        if (url.searchParams.get("debug") === "1") out0._usage = r.usage;
        return json(out0);
      }

      if (path === "/api/hooks-money" && request.method === "POST") {
        const body = await request.json();
        const story = String(body.story || "").trim();
        if (!story) return json({ error: "Isi dulu deskripsi ceritanya." }, 400);
        const r = await chat(
          HOOK_MODEL,
          [{ role: "user", content: SYSTEM + "\n\nDeskripsi:\n" + story }],
          apiKey
        );
        const out1 = { job_id: rid("m"), status: "done", ...parseHooks(r.content) };
        if (url.searchParams.get("debug") === "1") out1._usage = r.usage;
        return json(out1);
      }

      if (path === "/api/hooks-vision" && request.method === "POST") {
        const body = await request.json();
        const images = body.images;
        if (!images || !Array.isArray(images) || !images.length) {
          return json({ error: "Upload dulu minimal 1 screenshot." }, 400);
        }
        const content = [
          { type: "text", text: SYSTEM + "\n\nBuatkan hook untuk gambar-gambar ini." },
        ];
        let n = 0;
        for (const img of images.slice(0, 5)) {
          const durl = String((img && img.data_url) || "");
          if (durl.length < 1500) continue; // lewati placeholder 1x1
          if (!/^data:image\/(png|jpeg|webp|gif);base64,/.test(durl)) continue;
          content.push({ type: "image_url", image_url: { url: durl } });
          if (++n === 5) break;
        }
        if (!n) {
          return json({ error: "Tidak ada gambar valid untuk dianalisis." }, 400);
        }
        const r = await chat(VISION_MODEL, [{ role: "user", content }], apiKey);
        const out2 = { job_id: rid("v"), status: "done", ...parseHooks(r.content) };
        if (url.searchParams.get("debug") === "1") out2._usage = r.usage;
        return json(out2);
      }
    }

    return json({ error: "Tidak ditemukan." }, 404);
  } catch (e) {
    return json({ error: String((e && e.message) || e) }, 502);
  }
}
