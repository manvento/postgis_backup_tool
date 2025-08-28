# PostGIS Backup & Restore

Two command-line scripts to **dump** and **restore** a PostgreSQL/PostGIS database using native tools.
Connection parameters come from environment variables (JDBC-style). All prompts, comments and I/O are in English.

## Features
- Environment-driven config (JDBC-like `JDBC_URL`, `JDBC_USER`, `JDBC_PASSWORD`).
- **Native** backup/restore using `pg_dump` and `pg_restore` (works with geometry/geography types).
- Optional schema-only dump if `currentSchema` is present in the JDBC URL.
- Pre-restore safety: ensures `postgis` extension is present before restore.
- Confirmation prompts showing the target JDBC URL before executing.
  - Optional `FORCE_ROLE`: enforce a specific role during restore.
  - Optional `NO_OWNER`: ignore object ownership during restore.
  - `SCHEMA_MAP_FROM` and `SCHEMA_MAP_TO`: remap schema names during restore (useful when restoring into a different schema).

## Environment variables
Create a `.env` file or export the variables in your shell:
```
JDBC_PASSWORD=your_password
JDBC_URL='jdbc:postgresql://hostname:port/database?currentSchema=schema'
JDBC_USER=your_user
```

Additional optional environment variables:
```
FORCE_ROLE=your_role          # Force all restored objects to this role
NO_OWNER=true                 # If set, ignore object ownership
SCHEMA_MAP_FROM=old_schema    # Original schema name in the dump
SCHEMA_MAP_TO=new_schema      # Target schema name in the restore
```


## Prerequisites
- **PostgreSQL client tools**: `pg_dump`, `pg_restore`, and `psql` must be available in PATH.
- **PostGIS** installed on the server you are backing up from / restoring to.
- Python 3.9+.

### Install external tools (macOS)
```bash
brew install postgresql@17 postgis
```

### Install external tools (Debian/Ubuntu)
```bash
sudo apt-get update
sudo apt-get install -y postgresql-client postgis
```

Or run the helper script (tries to detect OS and install the needed client tools):
```bash
./setup_external_deps.sh
```

**Note**: if your are not using the helpser script, check that symbolic links are created or create by yourself (e.g. pg_dump for pg_dump-17, etc.).

## Python Setup

(Optional) Create and activate a virtual environment, then install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

### Dump (backup to a local file)
```bash
python dump.py /path/to/backup.dump
```

### Restore (from a local file)
```bash
python restore.py /path/to/backup.dump
```

## Notes on geometry support
- PostGIS types are fully preserved by `pg_dump/pg_restore`.
- Always ensure the `postgis` extension exists in the target database **before** restoring (the script does this automatically).
