"""Backup idempotente: pg_dump + snapshot de volúmenes (tar). Restaura con restore.py."""
import argparse, datetime, os, subprocess, sys
try:
    from scripts.compose_volumes import compose_volumes, volume_exists, running_services
except ModuleNotFoundError:
    from compose_volumes import compose_volumes, volume_exists, running_services

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


def main():
    ap = argparse.ArgumentParser(description="Backup Servator (DB + volúmenes)")
    ap.add_argument("--out", default="", help="directorio destino (defecto ./backups/<fecha>)")
    ap.add_argument("--db-only", action="store_true")
    ap.add_argument("--volumes-only", action="store_true")
    a = ap.parse_args()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = os.path.abspath(a.out or os.path.join(ROOT, "backups", stamp))
    os.makedirs(out, exist_ok=True)
    running = set()
    if not a.db_only:
        running = running_services()
        if {'backend', 'dispatcher', 'worker', 'worker-gpu', 'worker-setup'} & running:
            raise SystemExit('Detené backend, dispatcher y workers antes de respaldar base y archivos juntos. PostgreSQL debe quedar activo para db.sql.')
        if 's3mock' in running:
            raise SystemExit('Detené s3mock antes de copiar sus datos físicos.')
    if not a.volumes_only:
        # pg_dump vía contenedor postgres (idempotente: sobrescribe archivo del día)
        db_url = os.environ.get("DATABASE_URL", "")
        print(f"[backup] pg_dump -> {out}/db.sql")
        run(["docker", "compose", "exec", "-T", "postgres", "pg_dump", "--clean", "--if-exists", "-U",
             os.environ.get("POSTGRES_USER", "servator"), "-d",
             os.environ.get("POSTGRES_DB", "servator")],
            stdout=open(os.path.join(out, "db.sql"), "w", encoding="utf-8"))
    if not a.db_only:
        volumes = compose_volumes()
        for vol in ("pgdata", "redisdata", "s3mock-data", "servator-data", "model-cache"):
            if vol == 'pgdata' and not a.volumes_only:
                print('[backup] base respaldada mediante db.sql; se omite copia física de PostgreSQL activo')
                continue
            service = {'pgdata': 'postgres', 'redisdata': 'redis', 's3mock-data': 's3mock'}.get(vol)
            if service and service in running:
                print(f'[backup] {vol} se omite: {service} está activo y una copia física podría ser inconsistente')
                continue
            actual = volumes.get(vol)
            if not actual or not volume_exists(actual):
                print(f"[backup] volumen {vol} no existe; se omite")
                continue
            dest = os.path.join(out, f"{vol}.tar.gz")
            if os.path.isfile(dest):
                print(f"[backup] {vol} ya existe, se conserva")
                continue
            print(f"[backup] volumen {vol} -> {dest}")
            run(["docker", "run", "--rm", "-v", f"{actual}:/src:ro", "-v",
                 f"{out}:/dst", "alpine:3.20", "tar", "-czf", f"/dst/{vol}.tar.gz", "-C", "/src", "."])
    print(f"[backup] OK en {out}")


if __name__ == "__main__":
    main()
