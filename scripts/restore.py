"""Restore idempotente: restaura DB y/o volúmenes desde un dir de backup.
Nunca hace down -v. Pide confirmación salvo --yes."""
import argparse, os, subprocess
try:
    from scripts.compose_volumes import compose_volumes, volume_exists, running_services
except ModuleNotFoundError:
    from compose_volumes import compose_volumes, volume_exists, running_services

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=True, **kw)


def main():
    ap = argparse.ArgumentParser(description="Restore Servator desde backup")
    ap.add_argument("--src", required=True, help="directorio de backup (con db.sql y/o *.tar.gz)")
    ap.add_argument("--db-only", action="store_true")
    ap.add_argument("--volumes-only", action="store_true")
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    if not os.path.isdir(a.src):
        raise SystemExit(f"no existe {a.src}")
    if not a.yes:
        r = input(f"Restaurar desde {a.src}? Esto SOBRESCRIBE datos. [s/N]: ")
        if r.strip().lower() not in ("s", "si", "y", "yes"):
            print("cancelado"); return
    f = os.path.join(a.src, "db.sql")
    restoring_db = not a.volumes_only and os.path.isfile(f)
    targets = []
    if not a.db_only:
        import glob
        volumes = compose_volumes()
        allowed = {"pgdata", "redisdata", "s3mock-data", "servator-data", "model-cache"}
        source = os.path.abspath(a.src)
        for tar in sorted(glob.glob(os.path.join(a.src, "*.tar.gz"))):
            vol = os.path.basename(tar).removesuffix(".tar.gz")
            actual = volumes.get(vol) if vol in allowed else None
            if not actual:
                raise SystemExit(f"Archivo de volumen no reconocido: {os.path.basename(tar)}")
            if vol == 'pgdata' and restoring_db:
                print('[restore] se usa db.sql; se omite la copia física de PostgreSQL')
                continue
            if not volume_exists(actual):
                raise SystemExit(f"El volumen {actual} no existe. Iniciá primero el stack correspondiente.")
            targets.append((tar, vol, actual))
    running = running_services()
    app_services = {'backend', 'dispatcher', 'worker', 'worker-gpu', 'worker-setup'}
    if (restoring_db or targets) and app_services & running:
        raise SystemExit('Detené backend, dispatcher y workers antes de restaurar; conservá PostgreSQL activo para db.sql.')
    forbidden = {'pgdata': 'postgres', 'redisdata': 'redis', 's3mock-data': 's3mock', 'model-cache': 'paddle'}
    for _, vol, _ in targets:
        if forbidden.get(vol) in running:
            raise SystemExit(f"Detené {forbidden[vol]} antes de restaurar el volumen {vol}.")
    if restoring_db and 'postgres' not in running:
        raise SystemExit('PostgreSQL debe estar activo para restaurar db.sql.')
    if not a.volumes_only:
        if restoring_db:
            print(f"[restore] db.sql -> postgres")
            with open(f, "rb") as fh:
                run(["docker", "compose", "exec", "-T", "postgres", "psql", "-U",
                     os.environ.get("POSTGRES_USER", "servator"), "-d",
                     os.environ.get("POSTGRES_DB", "servator"), "-v", "ON_ERROR_STOP=1"], stdin=fh)
        else:
            print("[restore] sin db.sql, se omite DB")
    if not a.db_only:
        for tar, vol, actual in targets:
            print(f"[restore] {tar} -> volumen {actual}")
            run(["docker", "run", "--rm", "-v", f"{actual}:/dst", "-v", f"{source}:/src:ro",
                 "alpine:3.20", "sh", "-c",
                 'find /dst -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + && tar -xzf "$1" -C /dst',
                 "restore", f"/src/{vol}.tar.gz"])
    print("[restore] OK")


if __name__ == "__main__":
    main()
