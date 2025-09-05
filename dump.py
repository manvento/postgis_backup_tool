#!/usr/bin/env python
import os
import sys

from dotenv import load_dotenv

from pgback.env import ConfigError, resolve_pg_from_env
from pgback.io import confirm
from pgback.run import run


def main():
    load_dotenv()
    if len(sys.argv) != 2:
        print("Usage: python scripts/dump.py /path/to/backup.dump")
        sys.exit(2)
    out_file = sys.argv[1]
    try:
        info = resolve_pg_from_env()
    except ConfigError as e:
        print(f"[ERROR] {e}")
        sys.exit(2)
    confirm(info["jdbc_url"], "dump", out_file)
    uri = info["uri"]
    cmd = ["pg_dump", uri, "-f", out_file]
    if info["schema"]:
        cmd += ["-n", info["schema"]]

    # Skip schema creation statements if SKIP_SCHEMA is enabled (default: true)
    skip_schema = os.getenv("SKIP_SCHEMA", "true").lower() not in ("0", "false", "no")
    if skip_schema:
        cmd += ["--no-owner", "--no-privileges", "--no-tablespaces"]

    run(cmd)
    print("[INFO] Dump completed.")


if __name__ == "__main__":
    main()
