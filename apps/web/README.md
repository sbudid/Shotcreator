# ShotCreator Web App (Phase 2)

Frontend statis untuk ShotCreator — upload screenshot, isi/edit teks hook
(manual atau dibantu AI), tambah audio, render jadi video vertikal 1080×1920.

Vanilla HTML/CSS/JS, tanpa framework. Bisa di-host sebagai static site
(mis. Cloudflare Pages) dengan backend API terpisah.

**Catatan UX:** user TIDAK disuruh setting AI (provider/base URL/model/API key).
Cukup centang "Buatkan hook otomatis pakai AI" lalu isi deskripsi cerita.
Konfigurasi AI dipegang server via env vars.

## Jalankan lokal

Butuh backend API (dibuat di fase berikutnya). Untuk coba UI-nya saja:

```bash
cd apps/web
python3 -m http.server 8080
# buka http://localhost:8080
```

Halaman akan error saat memanggil `/api/...` kalau backend belum jalan —
itu normal, UI-nya tetap bisa dilihat.

## API contract (harus diimplementasikan backend)

### POST /api/hooks — generate teks hook dari cerita
Request:
```json
{
  "story": "deskripsi cerita dari screenshot"
}
```
Response:
```json
{"top_lines": ["BARIS ATAS 1", "BARIS ATAS 2"],
 "bot_lines": ["BARIS BAWAH 1", "BARIS BAWAH 2"]}
```

Konfigurasi AI (base URL, model, API key) dibaca server dari env vars
(`SHOTCREATOR_AI_*`) — tidak dikirim dari frontend. Kalau belum diset,
server return 400 `{"error": "AI belum dikonfigurasi di server..."}`.

### POST /api/jobs — buat job render
Request:
```json
{
  "images": [{"name": "ss1.png", "data_url": "data:image/png;base64,..."}],
  "top_lines": ["TEKS ATAS"],
  "bot_lines": ["TEKS BAWAH"],
  "audio": {"name": "musik.mp3", "data_url": "data:audio/mpeg;base64,..."} | null
}
```
Response: `{"job_id": "abc123"}`

Catatan: gambar & audio dikirim sebagai data URL base64 di JSON.
Untuk file besar, backend boleh menyediakan endpoint upload multipart
sebagai alternatif — frontend bisa disesuaikan nanti.

### GET /api/jobs/:id — status job
Response:
```json
{"status": "queued",    "progress": 0}
{"status": "rendering", "progress": 45}
{"status": "done",      "progress": 100, "video_url": "https://.../hasil.mp4"}
{"status": "error",     "error": "pesan error"}
```

`progress` 0–100. `video_url` boleh URL absolut atau path relatif.

## Perilaku AI di backend

- `POST /api/hooks` membaca konfigurasi AI dari env vars server
  (`SHOTCREATOR_AI_BASE_URL` wajib, `SHOTCREATOR_AI_API_KEY` /
  `SHOTCREATOR_AI_MODEL` opsional). Frontend tidak mengirim config AI.
- `POST /api/jobs` merender langsung pakai `top_lines`/`bot_lines`
  yang dikirim (engine deterministik, tanpa AI). Field `ai.*` dari client
  diabaikan.

## Struktur file

- `index.html` — UI utama (Bahasa Indonesia)
- `app.js` — logic: upload, panggil API, polling status, preview
- `styles.css` — tema gelap navy, mobile-first
