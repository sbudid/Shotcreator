# Shotcreator render worker: python + ffmpeg.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Engine package (build context = repo root).
COPY packages/engine ./packages/engine
RUN pip install --no-cache-dir ./packages/engine

COPY renderer/worker.py ./worker.py

ENV SHOTCREATOR_QUEUE_DIR=/queue
VOLUME ["/queue"]

CMD ["python", "worker.py"]
