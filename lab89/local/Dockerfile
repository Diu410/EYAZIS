FROM mirror.gcr.io/nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 HF_HOME=/models/huggingface
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python3 -m pip install --no-cache-dir faster-whisper==1.2.1
WORKDIR /app
COPY server.py /app/server.py
CMD ["python3", "/app/server.py"]
