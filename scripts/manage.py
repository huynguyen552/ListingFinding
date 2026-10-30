"""Local operations. Run from any directory; secrets are never printed."""

import argparse
import secrets
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True, **kwargs)


def initialize():
    target = ROOT / ".env"
    if target.exists():
        print("Da co .env; giu nguyen cau hinh.")
        return
    content = (
        (ROOT / ".env.example")
        .read_text(encoding="utf-8")
        .replace("replace_with_generated_password", secrets.token_hex(24))
    )
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    print("Da tao .env voi mat khau rieng. Khong dua file nay len Git.")


def backup():
    folder = ROOT / "backups"
    folder.mkdir(exist_ok=True)
    path = folder / ("leadfinder-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".dump")
    # Binary subprocess output avoids PowerShell redirection corrupting pg_dump.
    with path.open("xb") as stream:
        try:
            run(
                "exec",
                "-T",
                "postgres",
                "sh",
                "-c",
                'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"',
                stdout=stream,
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise
    print("Da sao luu:", path)


def verify_backup(path):
    path = Path(path).resolve(strict=True)
    if path.suffix != ".dump":
        raise SystemExit("Chi nhan file .dump.")
    # Restore into a separate temporary database, never overwrite the live one.
    name = "lf_restore_" + secrets.token_hex(6)
    run("exec", "-T", "postgres", "sh", "-c", f'createdb -U "$POSTGRES_USER" {name}')
    try:
        with path.open("rb") as stream:
            run(
                "exec",
                "-T",
                "postgres",
                "sh",
                "-c",
                f'pg_restore --exit-on-error --no-owner -U "$POSTGRES_USER" -d {name}',
                stdin=stream,
            )
        run(
            "exec",
            "-T",
            "postgres",
            "sh",
            "-c",
            f'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d {name} -c "SELECT count(*) AS locations FROM locations; SELECT version_num FROM alembic_version;"',
        )
        print("Phuc hoi thu thanh cong. Du lieu dang dung khong thay doi.")
    finally:
        run("exec", "-T", "postgres", "sh", "-c", f'dropdb -U "$POSTGRES_USER" {name}')


parser = argparse.ArgumentParser()
parser.add_argument(
    "action", choices=["init", "start", "stop", "status", "backup", "verify-backup"]
)
parser.add_argument("file", nargs="?")
args = parser.parse_args()
if args.action == "init":
    initialize()
elif args.action == "start":
    initialize()
    run("up", "-d", "--build", "--wait", "web")
    print("LeadFinder: http://localhost:5173")
elif args.action == "stop":
    run("stop")
elif args.action == "status":
    run("ps")
elif args.action == "backup":
    backup()
elif args.action == "verify-backup":
    if not args.file:
        parser.error("Can duong dan file .dump")
    verify_backup(args.file)
