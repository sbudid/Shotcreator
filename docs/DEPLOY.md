# Deploy Shotcreator

Arsitektur deploy: **frontend statis** + **API di mesin yang punya ffmpeg**.
Video encoding tidak bisa jalan di Cloudflare Workers/Pages — butuh proses
ffmpeg beneran, jadi API + renderer jalan di VPS/container.

```
[Browser] ──► Cloudflare Pages (apps/web: index.html/app.js/styles.css)
     │                │ fetch /api/…  (atau langsung ke API)
     ▼                ▼
[Cloudflare Worker (opsional proxy)] ──► VPS/container: python3 apps/api/server.py
                                              │ packages/engine + ffmpeg
                                              ▼
                                           ./data/videos/*.mp4
```

## 1. Frontend → Cloudflare Pages

`apps/web/` murni file statis (tanpa build step).

1. Di Cloudflare Dashboard → Pages → Create → hubungkan repo
   `sbudid/Shotcreator`, branch `main`.
2. **Build settings:** Framework preset `None`, Build command kosong,
   Output directory `apps/web`.
3. Deploy. Dapat URL mis. `https://shotcreator.pages.dev`.

### Arahkan frontend ke API

`apps/web/app.js` memanggil `/api/…` relatif. Dua opsi:

- **Opsi A (gampang):** serve web UI dari API server yang sama
  (`python3 server.py` juga serve `/`, `/app.js`, `/styles.css`). Tidak perlu
  Pages sama sekali — buka `http://VPS:8000/`.
- **Opsi B (Pages + VPS):** di `app.js`, ganti `fetch("/api/…")` menjadi
  `fetch("https://api-domain-kamu/api/…")`, atau pasang Worker proxy
  `/api/* → http://VPS:8000/api/*` supaya tetap same-origin.

## 2. API → VPS / container

Kebutuhan: Python 3.11+, `ffmpeg`, `Pillow`.

```bash
# di VPS
git clone https://github.com/sbudid/Shotcreator.git
cd Shotcreator/apps/api
pip install -r requirements.txt
sudo apt install -y ffmpeg   # atau sesuai distro

# env
export PORT=8000
export SHOTCREATOR_DATA=/var/lib/shotcreator/data
export SHOTCREATOR_FONT=/usr/share/fonts/inter/Inter-ExtraBold.ttf  # opsional
export SHOTCREATOR_AI_BASE_URL=http://localhost:20128/v1           # 9router
# SHOTCREATOR_AI_API_KEY sengaja TIDAK di-set di server:
# frontend mengirim api_key per-request (tidak disimpan di server).

python3 server.py
```

### systemd unit (contoh)

`/etc/systemd/system/shotcreator.service`:

```ini
[Unit]
Description=Shotcreator API
After=network.target

[Service]
User=shotcreator
WorkingDirectory=/opt/Shotcreator/apps/api
Environment=PORT=8000
Environment=SHOTCREATOR_DATA=/var/lib/shotcreator/data
Environment=SHOTCREATOR_FONT=/usr/share/fonts/inter/Inter-ExtraBold.ttf
Environment=SHOTCREATOR_AI_BASE_URL=http://localhost:20128/v1
ExecStart=/usr/bin/python3 server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now shotcreator
curl http://localhost:8000/api/health   # {"ok": true}
```

### Docker (contoh)

```dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . /app
WORKDIR /app/apps/api
RUN pip install --no-cache-dir -r requirements.txt
ENV PORT=8000 SHOTCREATOR_DATA=/data
VOLUME /data
EXPOSE 8000
CMD ["python3", "server.py"]
```

`/data` di-mount ke volume persisten supaya video hasil tidak hilang saat
container restart.

## 3. Kenapa bukan Workers?

Cloudflare Workers tidak bisa menjalankan binary `ffmpeg` dan tidak punya
filesystem untuk frame sementara. Pilihan yang realistis:

| Komponen | Tempat |
|---|---|
| Web UI (`apps/web`) | Cloudflare Pages (statis) |
| API + render (`apps/api` + `packages/engine`) | VPS / container (butuh ffmpeg) |
| Hasil video | Disk VPS (`SHOTCREATOR_DATA`) atau di-push ke R2 |
| Worker (opsional) | Proxy `/api/*` + auth di depan VPS |

## 4. R2 (opsional, untuk video hasil)

Kalau video hasil mau di-serve dari R2 (bukan disk VPS):

1. Buat bucket R2 di Cloudflare dashboard, dapat endpoint + API token.
2. Di VPS, sync `./data/videos/` ke R2 (mis. pakai `rclone` cron tiap menit).
3. `video_url` yang dikembalikan API (`/videos/<id>.mp4`) bisa diganti base
   URL publik R2 — atau biarkan API serve dari disk dan pasang cache
   Cloudflare di depannya.

## 5. Checklist sebelum go-live

- [ ] `ffmpeg` terinstal di mesin API (`ffmpeg -version`)
- [ ] `curl localhost:8000/api/health` → `{"ok": true}`
- [ ] Test render 1 gambar via web UI, cek `GET /api/jobs/:id` → `done`
- [ ] Kalau pakai Pages terpisah: CORS sudah `*` di server, atau Worker proxy
      sudah dipasang
- [ ] Firewall VPS: buka port API hanya dari Cloudflare / IP sendiri
      (atau pasang auth di reverse proxy untuk multi-user)
- [ ] Token Cloudflare: pastikan punya scope yang cukup (Account R2,
      Pages, Workers) sebelum mengotak-atik deploy via API
