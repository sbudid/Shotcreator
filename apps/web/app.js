/* ShotCreator web app — vanilla JS.
 * Konfigurasi AI (base_url, model, api_key) diset di server via env vars,
 * bukan oleh user. Frontend cuma kirim {story} ke /api/hooks.
 *
 * API contract:
 *   POST /api/hooks {story}
 *     -> {top_lines[], bot_lines[]}
 *   POST /api/jobs {images[], top_lines[], bot_lines[], audio?}
 *     -> {job_id}
 *   GET  /api/jobs/:id
 *     -> {status: "queued"|"rendering"|"done"|"error", progress?, video_url?, error?}
 */
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
    // Vision: kirim screenshot, money yang lihat dan buatkan hook
    if (!state.images.length) {
      btn.disabled = false;
      return setStatus("Upload dulu minimal 1 screenshot di bagian 1.", "error");
    }
    setStatus("AI sedang melihat screenshot… (sekitar 1 menit)");
    try {
      const res = await fetch("/api/hooks-vision", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          images: state.images.map((x) => ({ name: x.name, data_url: x.dataUrl })),
        }),
      });
      if (!res.ok) throw new Error("server: HTTP " + res.status);
      const data = await res.json();
      if (data.error || !data.job_id) throw new Error(data.error || "job_id tidak ada");
      await pollVisionHooks(data.job_id);
    } catch (err) {
      setStatus("Gagal membuat hook: " + err.message, "error");
      btn.disabled = false;
    }
    return;
  }

  // Text mode: dari deskripsi cerita via 9router
  if (mode === "text") {
    const story = $("story").value.trim();
    if (!story) {
      btn.disabled = false;
      return setStatus("Isi dulu deskripsi ceritanya.", "error");
    }
    setStatus("Membuat hook dengan AI…");
    try {
      const res = await fetch("/api/hooks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ story }),
      });
      if (!res.ok) throw new Error("server: HTTP " + res.status);
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      $("topLines").value = (data.top_lines || []).join("\n");
      $("botLines").value = (data.bot_lines || []).join("\n");
      setStatus("Hook berhasil dibuat. Cek & edit dulu kalau perlu, baru render.", "ok");
    } catch (err) {
      setStatus("Gagal membuat hook: " + err.message, "error");
    } finally {
      btn.disabled = false;
    }
    return;
  }

  // Money mode: dari deskripsi teks via antrean money
  if (mode === "money") {
    const story = $("story").value.trim();
    if (!story) {
      btn.disabled = false;
      return setStatus("Isi dulu deskripsi ceritanya.", "error");
    }
    setStatus("AI money sedang membuat hook… (sekitar 1 menit)");
    try {
      const res = await fetch("/api/hooks-money", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ story }),
      });
      if (!res.ok) throw new Error("server: HTTP " + res.status);
      const data = await res.json();
      if (data.error || !data.job_id) throw new Error(data.error || "job_id tidak ada");
      await pollMoneyHooks(data.job_id);
    } catch (err) {
      setStatus("Gagal membuat hook: " + err.message, "error");
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

    setStatus("AI sedang melihat hasil capture… (sekitar 1 menit)", "");
    const res = await fetch("/api/hooks-vision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ images: [{ name: "capture.png", data_url: dataUrl }] }),
    });
    if (!res.ok) throw new Error("server: HTTP " + res.status);
    const data = await res.json();
    if (data.error || !data.job_id) throw new Error(data.error || "job_id tidak ada");
    // pakai polling yang sama dengan vision manual
    $("btnGenHooks").disabled = true;
    await pollVisionHooks(data.job_id);
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

async function pollVisionHooks(jobId) {
  const btn = $("btnGenHooks");
  for (let i = 0; i < 40; i++) {  // maks ~2 menit
    await new Promise((r) => setTimeout(r, 3000));
    try {
      const res = await fetch("/api/hooks-vision/" + encodeURIComponent(jobId));
      if (!res.ok) continue;
      const data = await res.json();
      if (data.status === "done") {
        $("topLines").value = (data.top_lines || []).join("\n");
        $("botLines").value = (data.bot_lines || []).join("\n");
        setStatus("Hook berhasil dibuat dari screenshot. Cek & edit dulu kalau perlu.", "ok");
        btn.disabled = false;
        return;
      }
      if (data.status === "error") throw new Error(data.error || "gagal");
      setStatus(`AI sedang melihat screenshot… (${i * 3} detik)`);
    } catch (err) {
      if (err.message && !err.message.includes("HTTP")) throw err;
    }
  }
  setStatus("AI-nya kelamaan. Coba lagi atau pakai mode teks.", "error");
  btn.disabled = false;
}

async function pollMoneyHooks(jobId) {
  const btn = $("btnGenHooks");
  for (let i = 0; i < 40; i++) {  // maks ~2 menit
    await new Promise((r) => setTimeout(r, 3000));
    try {
      const res = await fetch("/api/hooks-money/" + encodeURIComponent(jobId));
      if (!res.ok) continue;
      const data = await res.json();
      if (data.status === "done") {
        $("topLines").value = (data.top_lines || []).join("\n");
        $("botLines").value = (data.bot_lines || []).join("\n");
        setStatus("Hook berhasil dibuat AI money. Cek & edit dulu kalau perlu.", "ok");
        btn.disabled = false;
        return;
      }
      if (data.status === "error") throw new Error(data.error || "gagal");
      setStatus(`AI money sedang membuat hook… (${i * 3} detik)`);
    } catch (err) {
      if (err.message && !err.message.includes("HTTP")) throw err;
    }
  }
  setStatus("AI-nya kelamaan. Coba lagi.", "error");
  btn.disabled = false;
}

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

  const payload = {
    images: state.images.map((x) => ({ name: x.name, data_url: x.dataUrl })),
    top_lines: top,
    bot_lines: bot,
    audio: state.audio ? { name: state.audio.name, data_url: state.audio.dataUrl } : null,
  };

  const btn = $("btnRender");
  btn.disabled = true;
  $("jobCard").classList.remove("hidden");
  $("preview").classList.add("hidden");
  $("btnDownload").classList.add("hidden");
  setJobStatus("queued", 0);
  setStatus("Mengirim job render…");

  try {
    const res = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("server: HTTP " + res.status);
    const data = await res.json();
    if (data.error || !data.job_id) throw new Error(data.error || "job_id tidak ada");
    setStatus("Job terkirim. Merender…", "ok");
    startPolling(data.job_id);
  } catch (err) {
    setStatus("Gagal mengirim job: " + err.message, "error");
    btn.disabled = false;
  }
});

function setJobStatus(status, progress) {
  $("jobLabel").textContent = STATUS_LABEL[status] || status;
  $("progressBar").style.width = Math.max(0, Math.min(100, progress || 0)) + "%";
}

function startPolling(jobId) {
  stopPolling();
  const tick = async () => {
    try {
      const res = await fetch("/api/jobs/" + encodeURIComponent(jobId));
      if (!res.ok) throw new Error("HTTP " + res.status);
      const job = await res.json();
      setJobStatus(job.status, job.progress);
      if (job.status === "done") {
        stopPolling();
        $("btnRender").disabled = false;
        if (job.video_url) {
          $("preview").src = job.video_url;
          $("preview").classList.remove("hidden");
          const dl = $("btnDownload");
          dl.href = job.video_url;
          dl.classList.remove("hidden");
          setStatus("Video selesai! Putar preview atau download.", "ok");
        } else {
          setStatus("Job selesai tapi video_url kosong.", "error");
        }
        $("jobCard").scrollIntoView({ behavior: "smooth" });
      } else if (job.status === "error") {
        stopPolling();
        $("btnRender").disabled = false;
        setStatus("Render gagal: " + (job.error || "tidak diketahui"), "error");
      }
      // queued/rendering -> terus polling
    } catch (err) {
      // error jaringan sesaat: biarkan polling jalan, tampilkan sekali
      setStatus("Menunggu server… (" + err.message + ")");
    }
  };
  tick();
  state.pollTimer = setInterval(tick, 2500);
}

function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}
window.addEventListener("beforeunload", stopPolling);
