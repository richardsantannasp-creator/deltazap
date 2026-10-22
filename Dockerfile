# Servidor do SDR (painel + API). Dados ficam em /data (volume).
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 DB_PATH=/data/sdr.db UPLOADS_DIR=/data/uploads BACKUP_DIR=/data/backups
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/* && pip install -r requirements.txt
COPY server.py places_core.py places_enrich.py dashboard.html atendente.html gestor.html sdr_prompt.txt sdr_knowledge.md restore_backup.py ./
COPY niches ./niches
COPY static ./static
RUN useradd -m -u 10001 sdr && mkdir -p /data && chown sdr /data
USER sdr
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=4).status==200 else 1)"
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
