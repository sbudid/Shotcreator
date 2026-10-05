/* ShotCreator web app — vanilla JS. VERSI GRATIS: tanpa AI, 100% client-side.
 * Upload screenshot, tulis hook manual, render video di browser. */
"use strict";

const $ = (id) => document.getElementById(id);

const state = {
  images: [],   // {id, name, dataUrl}
  audio: null,  // {name, dataUrl}
  pollTimer: null,
};

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
