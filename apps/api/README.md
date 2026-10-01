# Shotcreator API

Backend HTTP untuk Shotcreator — menerima job render dari web UI (`apps/web`)
atau request langsung, merender video pakai `packages/engine` + ffmpeg di
background thread.

Server-nya sendiri **stdlib-only** (tanpa Flask/FastAPI). Engine butuh
`Pillow` (lihat `requirements.txt`) dan `ffmpeg` di PATH.

## Jalankan

```bash
cd apps/api
pip install -r requirements.txt   # Pillow
python3 server.py
```

Buka `http://localhost:8000/` — web UI ikut diserve dari server yang sama,
jadi bisa langsung dipakai standalone.

## Env vars

| Var | Default | Keterangan |
|---|---|---|
| `PORT` | `8000` | Port HTTP |
| `SHOTCREATOR_DATA` | `./data` | Direktori job & video hasil |
| `SHOTCREATOR_FONT` | DejaVuSans-Bold | Font bold untuk teks hook (mis. path Inter ExtraBold) |
| `SHOTCREATOR_AI_BASE_URL` | — | Default base URL AI (dipakai kalau request tidak kirim `api_key`/base_url). Mis. `http://localhost:20128/v1` untuk 9router |
| `SHOTCREATOR_AI_API_KEY` | — | Default API key AI |
| `SHOTCREATOR_AI_MODEL` | — | Default model AI |

## Endpoint

- `POST /api/hooks` — `{ai:{mode,provider,base_url,model,api_key?}, story}` → `{top_lines[], bot_lines[]}`
- `POST /api/jobs` — `{images:[{name, data_url}], top_lines[], bot_lines[], audio?, ai:{...}, pan_secs?}` → `{job_id}` (202)
- `GET /api/jobs/:id` — `{status: queued|rendering|done|error, progress?, video_url?, top_lines?, bot_lines?, error?}`
- `GET /videos/:file` — file mp4
- `GET /api/health` — `{ok: true}`

`images[].data_url` dan `audio.data_url` berupa **data URL base64**
(mis. `data:image/png;base64,…`). Maks 30 MB per file, 200 MB per request,
maks 20 gambar per job.

Semua error dikembalikan sebagai JSON `{error: "…"}` (Bahasa Indonesia)
dengan status code yang tepat (400 validasi, 404 tidak ada, 502 AI gagal,
500 server error).

## Catatan

- Job dirender di background thread; progress diestimasi dari total durasi
  (dwell + pan). Status akhir (`done`/`error`) disimpan ke disk, jadi tetap
  bisa di-query setelah server restart — tapi job yang sedang jalan saat
  restart tidak dilanjutkan otomatis.
- CORS terbuka (`*`) supaya web UI dari Cloudflare Pages bisa memanggil API
  di VPS.
- Jangan expose langsung ke internet tanpa reverse proxy + auth kalau dipakai
  multi-user; untuk pemakaian pribadi cukup batasi firewall.
