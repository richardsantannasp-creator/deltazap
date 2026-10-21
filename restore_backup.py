"""Restaura um backup do SDR WhatsApp (.zip gerado pelo painel).
Uso:  python restore_backup.py backups/sdr-20261020-030000.zip [pasta-destino]
PARE o sistema antes. O banco atual é guardado como sdr.db.antes-da-restauracao-AAAAMMDD-HHMMSS."""
import sys, zipfile, shutil, time
from pathlib import Path

def restore(zip_path, target):
    target = Path(target).resolve()
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        if "sdr.db" not in names:
            raise SystemExit("Este arquivo não parece um backup do SDR (falta sdr.db).")
        for n in names:                                   # proteção contra caminhos maliciosos dentro do zip
            dest = (target / n).resolve()
            if not str(dest).startswith(str(target)) or n.startswith("/"):
                raise SystemExit(f"Arquivo suspeito no backup: {n}")
        db = target / "sdr.db"
        if db.exists():
            shutil.copy2(db, target / ("sdr.db.antes-da-restauracao-" + time.strftime("%Y%m%d-%H%M%S")))
        for ext in ("-wal", "-shm"):
            (target / ("sdr.db" + ext)).unlink(missing_ok=True)
        z.extract("sdr.db", target)
        n_up = 0
        for n in names:
            if n.startswith("uploads/") and not n.endswith("/"):
                z.extract(n, target); n_up += 1
    return n_up

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    up = restore(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else Path(__file__).parent)
    print(f"Restaurado: banco de dados e {up} arquivo(s) anexo(s). Agora você pode iniciar o sistema.")
