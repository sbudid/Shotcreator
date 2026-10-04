/* ShotCreator web app — vanilla JS.
 * AI 100% client-side: browser memanggil langsung api.commandcode.ai
 * (OpenAI-compatible). API key milik user, disimpan di localStorage
 * browser ini saja — tidak dikirim ke mana pun selain command-code.
 * Render video juga 100% di browser (tanpa server).
 */
"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  images: [],   // {id, name, dataUrl}
  audio: null,  // {name, dataUrl}
  pollTimer: null,
};

/* ---------- AI langsung via command-code (tanpa backend) ---------- */
const CC_BASE = "https://api.commandcode.ai/provider/v1";
const CC_HOOK_MODEL = "deepseek/deepseek-v4-flash";   // hook dari teks
const CC_VISION_MODEL = "google/gemini-3.8-flash";    // hook dari gambar
const CC_SYS =
  "Kamu penulis hook video vertikal TikTok/Reels berbahasa Indonesia. " +
  "Balas HANYA dengan JSON seperti ini: " +
  '{"top": ["BARIS ATAS 1", "BARIS ATAS 2"], "bottom": ["BARIS BAWAH"]}. ' +
  "Huruf kapital semua, tiap baris maksimal 28 karakter, 1-2 baris per " +
  "bagian, gaya bikin penasaran dan emosional. " +
  "JANGAN mengklaim pengalaman pribadi seperti 'aku pakai' atau 'favoritku'.";

function ccGetKey() { return (localStorage.getItem("cc_api_key") || "").trim(); }
function ccSetKey(v) { localStorage.setItem("cc_api_key", (v || "").trim()); }

async function ccChat(model, messages) {
  const key = ccGetKey();
  if (!key) {
    throw new Error("Isi dulu API key command-code di bagian 3 (tersimpan di browser ini saja).");
  }
  const res = await fetch(CC_BASE + "/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": "Bearer " + key,
    },
    body: JSON.stringify({ model, messages, temperature: 0.7 }),
  });
  if (!res.ok) {
    const t = (await res.text()).slice(0, 160);
    throw new Error("AI HTTP " + res.status + (t ? ": " + t : ""));
  }
  const data = await res.json();
  const c = data && data.choices && data.choices[0] &&
    data.choices[0].message && data.choices[0].message.content;
  if (!c) throw new Error("Respons AI tak terduga.");
  return c;
}

function ccParseHooks(text) {
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
  const bot = norm(obj.bottom);
  if (!top.length || !bot.length) {
    throw new Error("AI tidak mengembalikan hook yang valid.");
  }
  return { top, bot };
}

function ccFillHooks(hooks, okMsg) {
  $("topLines").value = hooks.top.join("\n");
  $("botLines").value = hooks.bot.join("\n");
  setStatus(okMsg, "ok");
  $("btnGenHooks").disabled = false;
}

// Isi field key dari localStorage saat halaman dibuka
document.addEventListener("DOMContentLoaded", () => {
  const k = $("aiKey");
  if (k) {
    k.value = ccGetKey();
    k.addEventListener("change", () => {
      ccSetKey(k.value);
      setStatus("API key tersimpan di browser ini.", "ok");
    });
  }
  const dk = $("btnDelKey");
  if (dk) dk.addEventListener("click", () => {
    localStorage.removeItem("cc_api_key");
    const k = $("aiKey");
    if (k) k.value = "";
    setStatus("API key dihapus dari browser ini.", "ok");
  });
});

/* ---------- helpers ---------- */
function setStatus(msg, kind) {
  const el = $("status");
  el.textContent = msg;
  el.className = "status" + (kind ? " " + kind : "");
  el.classList.remove("hidden");
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}
function clearStatus() { $("status").classList.add("hidden"); }

function readAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(new Error("Gagal membaca file " + file.name));
    r.readAsDataURL(file);
  });
}

function linesOf(id) {
  return $(id).value.split("\n").map((s) => s.trim()).filter(Boolean);
}

function aiEnabled() {
  return $("aiToggle").checked; // true | false
}

/* ---------- images ---------- */
$("imageInput").addEventListener("change", async (e) => {
  const files = Array.from(e.target.files || []);
  for (const f of files) {
    try {
      const dataUrl = await readAsDataURL(f);
      state.images.push({ id: Math.random().toString(36).slice(2), name: f.name, dataUrl });
    } catch (err) {
      setStatus(err.message, "error");
    }
  }
  e.target.value = "";
  renderThumbs();
});

function renderThumbs() {
  const box = $("thumbs");
  box.innerHTML = "";
  state.images.forEach((img, i) => {
    const d = document.createElement("div");
    d.className = "thumb";
    const im = document.createElement("img");
    im.src = img.dataUrl;
    im.alt = img.name;
    const num = document.createElement("span");
    num.className = "num";
    num.textContent = i + 1;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "×";
    btn.title = "Hapus gambar ini";
    btn.addEventListener("click", () => {
      state.images = state.images.filter((x) => x.id !== img.id);
      renderThumbs();
    });
    d.append(im, num, btn);
    box.appendChild(d);
  });
}

/* ---------- audio ---------- */
$("audioInput").addEventListener("change", async (e) => {
  const f = e.target.files && e.target.files[0];
  e.target.value = "";
  if (!f) return;
  try {
    const dataUrl = await readAsDataURL(f);
    state.audio = { name: f.name, dataUrl };
    $("audioName").textContent = "🎵 " + f.name;
    $("audioInfo").classList.remove("hidden");
  } catch (err) {
    setStatus(err.message, "error");
  }
});
$("btnClearAudio").addEventListener("click", () => {
  state.audio = null;
  $("audioInfo").classList.add("hidden");
});

/* ---------- AI toggle ---------- */
$("aiToggle").addEventListener("change", () => {
  $("aiConfig").classList.toggle("hidden", !aiEnabled());
});

/* ---------- AI mode radio ---------- */
document.querySelectorAll('input[name="aiMode"]').forEach((r) => {
  r.addEventListener("change", () => {
    const mode = document.querySelector('input[name="aiMode"]:checked').value;
    $("visionDesc").classList.toggle("hidden", mode !== "vision");
    $("textDesc").classList.toggle("hidden", mode !== "text" && mode !== "money");
    $("moneyDesc").classList.toggle("hidden", mode !== "money");
  });
});

function aiMode() {
  const el = document.querySelector('input[name="aiMode"]:checked');
  return el ? el.value : "vision";
}

/* ---------- generate hooks ---------- */
$("btnGenHooks").addEventListener("click", async () => {
  const btn = $("btnGenHooks");
  btn.disabled = true;
  const mode = aiMode();

  if (mode === "vision") {
    // Vision: AI melihat screenshot langsung via command-code
    if (!state.images.length) {
      btn.disabled = false;
      return setStatus("Upload dulu minimal 1 screenshot di bagian 1.", "error");
    }
    setStatus("AI sedang melihat screenshot…");
    try {
      const content = [
        { type: "text", text: CC_SYS + "\n\nBuatkan hook untuk gambar-gambar ini." },
      ];
      let n = 0;
      for (const x of state.images.slice(0, 5)) {
        const durl = x.dataUrl || "";
        if (durl.length < 1500) continue; // lewati placeholder 1x1
        if (!/^data:image\/(png|jpeg|webp|gif);base64,/.test(durl)) continue;
        content.push({ type: "image_url", image_url: { url: durl } });
        if (++n === 5) break;
      }
      if (!n) throw new Error("Tidak ada gambar valid untuk dianalisis.");
      const text = await ccChat(CC_VISION_MODEL, [{ role: "user", content }]);
      ccFillHooks(
        ccParseHooks(text),
        "Hook berhasil dibuat dari screenshot. Cek & edit dulu kalau perlu."
      );
    } catch (err) {
      setStatus("Gagal membuat hook: " + err.message, "error");
      btn.disabled = false;
    }
    return;
  }

  // Text mode: dari deskripsi cerita via command-code (deepseek flash)
  if (mode === "text") {
    const story = $("story").value.trim();
    if (!story) {
      btn.disabled = false;
      return setStatus("Isi dulu deskripsi ceritanya.", "error");
    }
    setStatus("Membuat hook dengan AI…");
    try {
      const text = await ccChat(CC_HOOK_MODEL, [
        { role: "user", content: CC_SYS + "\n\nDeskripsi:\n" + story },
      ]);
      ccFillHooks(
        ccParseHooks(text),
        "Hook berhasil dibuat. Cek & edit dulu kalau perlu, baru render."
      );
    } catch (err) {
      setStatus("Gagal membuat hook: " + err.message, "error");
    } finally {
      btn.disabled = false;
    }
    return;
  }

  // Money mode: dari deskripsi teks via command-code (deepseek flash)
  if (mode === "money") {
    const story = $("story").value.trim();
    if (!story) {
      btn.disabled = false;
      return setStatus("Isi dulu deskripsi ceritanya.", "error");
    }
    setStatus("AI money sedang membuat hook…");
    try {
      const text = await ccChat(CC_HOOK_MODEL, [
        { role: "user", content: CC_SYS + "\n\nDeskripsi:\n" + story },
      ]);
      ccFillHooks(
        ccParseHooks(text),
        "Hook berhasil dibuat AI money. Cek & edit dulu kalau perlu."
      );
    } catch (err) {
      setStatus("Gagal membuat hook: " + err.message, "error");
    } finally {
      btn.disabled = false;
    }
    return;
  }
});

/* ---------- capture layar otomatis -> vision ---------- */
$("btnCapture").addEventListener("click", async () => {
  const btn = $("btnCapture");
  btn.disabled = true;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
    setStatus("Browser tidak mendukung capture layar. Pakai upload manual di bagian 1.", "error");
    btn.disabled = false;
    return;
  }
  let stream = null;
  try {
    setStatus("Pilih jendela/tab yang mau di-capture…", "");
    stream = await navigator.mediaDevices.getDisplayMedia({ video: true, audio: false });
    const video = document.createElement("video");
    video.srcObject = stream;
    await video.play();
    await new Promise((r) => setTimeout(r, 500)); // tunggu frame stabil
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    const dataUrl = canvas.toDataURL("image/png");
    stream.getTracks().forEach((t) => t.stop());
    stream = null;

    setStatus("AI sedang melihat hasil capture…", "");
    const text = await ccChat(CC_VISION_MODEL, [
      {
        role: "user",
        content: [
          { type: "text", text: CC_SYS + "\n\nBuatkan hook untuk gambar ini." },
          { type: "image_url", image_url: { url: dataUrl } },
        ],
      },
    ]);
    const hooks = ccParseHooks(text);
    $("topLines").value = hooks.top.join("\n");
    $("botLines").value = hooks.bot.join("\n");
    setStatus("Hook berhasil dibuat dari hasil capture. Cek & edit dulu kalau perlu.", "ok");
    $("btnGenHooks").disabled = false;
  } catch (err) {
    if (stream) stream.getTracks().forEach((t) => t.stop());
    if (err.name === "NotAllowedError") {
      setStatus("Capture dibatalkan.", "error");
    } else {
      setStatus("Gagal capture: " + err.message, "error");
    }
  }
  btn.disabled = false;
});

/* ---------- render job ---------- */
const STATUS_LABEL = {
  queued: "⏳ Menunggu antrean…",
  rendering: "🎞️ Merender video…",
  done: "✅ Selesai!",
  error: "❌ Gagal",
};

$("btnRender").addEventListener("click", async () => {
  clearStatus();
  if (!state.images.length) return setStatus("Upload dulu minimal 1 screenshot.", "error");

  const top = linesOf("topLines");
  const bot = linesOf("botLines");

  if (!top.length || !bot.length) {
    return setStatus(
      "Isi teks hook atas & bawah — ketik manual, atau centang AI lalu klik \u201cBuatkan hook\u201d.",
      "error"
    );
  }

  const btn = $("btnRender");
  btn.disabled = true;
  $("jobCard").classList.remove("hidden");
  $("preview").classList.add("hidden");
  $("btnDownload").classList.add("hidden");
  setJobStatus("rendering", 0);
  setStatus("🎞️ Merender di perangkatmu… jangan tutup tab ini.", "");

  // Render 100% di browser — tanpa server.
  try {
    const { blob, ext } = await crRender({
      images: state.images.map((x) => x.dataUrl),
      topLines: top,
      botLines: bot,
      audioDataUrl: state.audio ? state.audio.dataUrl : null,
      onProgress: (p) => setJobStatus("rendering", Math.round(p * 100)),
    });
    const url = URL.createObjectURL(blob);
    const fname = "shotcreator." + ext;
    $("preview").src = url;
    $("preview").classList.remove("hidden");
    const dl = $("btnDownload");
    dl.href = url;
    dl.download = fname;
    dl.classList.remove("hidden");
    setJobStatus("done", 100);
    setStatus(`Video selesai! Format ${ext.toUpperCase()} — putar preview atau download.`, "ok");
    $("jobCard").scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    setJobStatus("error", 0);
    setStatus("Render gagal: " + err.message, "error");
  }
  btn.disabled = false;
});

function setJobStatus(status, progress) {
  $("jobLabel").textContent = STATUS_LABEL[status] || status;
  $("progressBar").style.width = Math.max(0, Math.min(100, progress || 0)) + "%";
}
