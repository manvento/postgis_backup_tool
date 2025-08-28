#!/usr/bin/env python
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dotenv import load_dotenv

from pgback.env import ConfigError, host_is_resolvable, resolve_pg_from_env
from pgback.io import confirm
from pgback.run import run


# --- Optional behavior toggles via environment ---
# Force object ownership (we'll do SET ROLE <role>; and strip OWNER statements if NO_OWNER=1)
FORCE_ROLE = os.getenv("FORCE_ROLE")
NO_OWNER = os.getenv("NO_OWNER", "1").lower() not in ("0", "false", "no")

# Direct schema remap inside the plain SQL (no CREATE/RENAME SCHEMA)
# Example: SCHEMA_MAP_FROM=myschema_in_dump  SCHEMA_MAP_TO=public
SCHEMA_MAP_FROM = os.getenv("SCHEMA_MAP_FROM")
SCHEMA_MAP_TO   = os.getenv("SCHEMA_MAP_TO")


def run_capture(cmd: list[str]) -> tuple[int, str]:
    """
    Run a command and capture combined stdout/stderr without raising.
    Returns (returncode, output_text).
    """
    print("[INFO]", " ".join(shlex.quote(c) for c in cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out, _ = p.communicate()
    if out:
        print(out, end="")
    return p.returncode, out or ""


def schema_exists(uri: str, schema: str) -> bool:
    # `psql -tAc` prints '1' for a row, empty for none. Exit code is 0 either way.
    sql = f"SELECT 1 FROM information_schema.schemata WHERE schema_name = '{schema}';"
    rc, out = run_capture(["psql", uri, "-tAc", sql])
    if rc != 0:
        # If psql itself failed (bad URI etc.), treat as not existing to keep a clear error later
        return False
    return out.strip() == "1"


def is_plain_sql_file(path: str) -> bool:
    """
    Heuristic: try to read a small chunk and see if it looks like text (not a custom/binary archive).
    Custom (-F c) archives are binary and won't decode as UTF-8 cleanly.
    """
    try:
        with open(path, "rb") as f:
            chunk = f.read(2048)
        # If this decodes as UTF-8 and contains typical SQL markers, assume plain SQL
        text = chunk.decode("utf-8", errors="strict")
        return True
    except Exception:
        return False


def preprocess_plain_sql(sql_text: str, src_schema: str | None, dst_schema: str | None) -> str:
    """
    Rewrite the plain SQL:
      - Optionally SET ROLE <FORCE_ROLE>;
      - Optionally strip OWNER/privilege statements if NO_OWNER=1;
      - Ensure PostGIS extensions are not (re)created here (we handle them separately);
      - If src_schema/dst_schema are provided, rewrite:
          * CREATE/ALTER/COMMENT SCHEMA on src_schema -> remove
          * SET search_path = src_schema, pg_catalog -> dst_schema, pg_catalog
          * Qualified names src_schema.* -> "dst_schema".*
    """
    out = sql_text

    # 1) PostGIS extensions: remove create/alter/comment (we ensure postgis outside)
    postgis_exts = ("postgis", "postgis_topology", "fuzzystrmatch", "postgis_tiger_geocoder")
    for ext in postgis_exts:
        out = re.sub(rf'(?is)^\s*CREATE\s+EXTENSION\b.*\b{ext}\b.*?;\s*', "", out)
        out = re.sub(rf'(?is)^\s*ALTER\s+EXTENSION\b.*\b{ext}\b.*?;\s*', "", out)
        out = re.sub(rf'(?is)^\s*COMMENT\s+ON\s+EXTENSION\s+{ext}\s+IS\s+.*?;\s*', "", out)

    # 2) If NO_OWNER, strip ALTER ... OWNER TO ..., SET OWNER TO, REVOKE/GRANT OWNERSHIP patterns
    if NO_OWNER:
        # Simple and pragmatic: drop common ALTER OWNER statements
        out = re.sub(r'(?im)^\s*ALTER\s+(TABLE|SEQUENCE|VIEW|MATERIALIZED\s+VIEW|FUNCTION|TYPE|SCHEMA|DATABASE|INDEX)\s+.*\s+OWNER\s+TO\s+.*?;\s*', "", out)
        # Also drop COMMENT ON EXTENSION ownership comments (rare, but harmless to remove)
        out = re.sub(r'(?im)^\s*COMMENT\s+ON\s+(TABLE|SEQUENCE|VIEW|MATERIALIZED\s+VIEW|FUNCTION|TYPE|SCHEMA|DATABASE|INDEX)\s+.*?;\s*', r'\g<0>', out)  # keep comments; we don't remove these broadly

    # 3) Schema rewrite
    if src_schema and dst_schema:
        # Remove CREATE/ALTER/COMMENT SCHEMA for src_schema
        patterns_drop = [
            rf'(?im)^\s*CREATE\s+SCHEMA\s+("?{re.escape(src_schema)}"?).*?;\s*$',
            rf'(?im)^\s*ALTER\s+SCHEMA\s+("?{re.escape(src_schema)}"?)\s+OWNER\s+TO\s+.*?;\s*$',
            rf'(?im)^\s*COMMENT\s+ON\s+SCHEMA\s+("?{re.escape(src_schema)}"?)\s+IS\s+.*?;\s*$',
        ]
        for pat in patterns_drop:
            out = re.sub(pat, "", out)

        # Rewrite SET search_path
        out = re.sub(
            rf'(?im)^\s*SET\s+search_path\s*=\s*"{re.escape(src_schema)}"\s*,\s*pg_catalog\s*;\s*$',
            f'SET search_path = "{dst_schema}", pg_catalog;',
            out,
        )
        out = re.sub(
            rf'(?im)^\s*SET\s+search_path\s*=\s*{re.escape(src_schema)}\s*,\s*pg_catalog\s*;\s*$',
            f'SET search_path = {dst_schema}, pg_catalog;',
            out,
        )

        # Rewrite qualified names: "src".foo -> "dst".foo   and   src.foo -> "dst".foo
        def _repl(_m):
            return f'"{dst_schema}".'

        out = re.sub(rf'(?<![\w"])("{re.escape(src_schema)}")\.', _repl, out)
        out = re.sub(rf'(?<![\w"])({re.escape(src_schema)})\.', _repl, out)

    # 4) Prepend SET ROLE if requested
    if FORCE_ROLE:
        out = f'SET ROLE {FORCE_ROLE};\n{out}'

    return out


def main():
    load_dotenv()

    if len(sys.argv) != 2:
        print("Usage: python restore.py /path/to/backup.sql")
        sys.exit(2)

    dump_file = sys.argv[1]
    if not os.path.isfile(dump_file):
        print(f"[ERROR] Backup file not found: {dump_file}")
        sys.exit(2)

    # Ensure this is a plain-text SQL file, not a custom (-F c) archive
    if not is_plain_sql_file(dump_file):
        print("[ERROR] This restore expects a Plain-Text SQL dump file. Your file does not look like plain SQL.")
        print("        Re-create the dump without '-F c' (custom format), e.g.: pg_dump ... > backup.sql")
        sys.exit(2)

    try:
        info = resolve_pg_from_env()
    except ConfigError as e:
        print(f"[ERROR] {e}")
        sys.exit(2)

    confirm(info["jdbc_url"], "restore INTO", dump_file)

    # Early, helpful error if hostname is not reachable
    if not host_is_resolvable(info["host"]):
        print(f"[ERROR] Host '{info['host']}' from SYSTEM_JDBC_URL is not resolvable on this machine.")
        print("Tips: use a reachable hostname/IP (e.g., 'localhost'), add a hosts entry, or ensure your Docker network name is resolvable.")
        sys.exit(2)

    uri = info["uri"]
    target_schema = (info["schema"] or "public").strip()

    # Ensure PostGIS is present
    run(["psql", uri, "-c", "CREATE EXTENSION IF NOT EXISTS postgis;"])

    # If we’re remapping schema, ensure destination exists (we won’t CREATE it here)
    if SCHEMA_MAP_FROM and SCHEMA_MAP_TO:
        if not schema_exists(uri, SCHEMA_MAP_TO):
            print(f"[ERROR] Destination schema '{SCHEMA_MAP_TO}' does not exist (or cannot be checked). Please create it first or choose another.")
            sys.exit(2)

    # Load plain SQL, preprocess (schema remap / ownership / extensions), write to temp, execute
    with open(dump_file, "r", encoding="utf-8") as f:
        sql_text = f.read()

    processed = preprocess_plain_sql(
        sql_text=sql_text,
        src_schema=SCHEMA_MAP_FROM,
        dst_schema=SCHEMA_MAP_TO or target_schema  # if no explicit map TO, default to target schema
    )

    with tempfile.NamedTemporaryFile("w", delete=False, prefix="restore_", suffix=".sql") as ftmp:
        ftmp.write(processed)
        sql_path = ftmp.name

    try:
        # ON_ERROR_STOP=1 stops on first error to avoid half-applied restores
        run(["psql", uri, "-v", "ON_ERROR_STOP=1", "-f", sql_path])
    finally:
        try:
            os.remove(sql_path)
        except OSError:
            pass

    print("[INFO] Restore completed.")


if __name__ == "__main__":
    main()