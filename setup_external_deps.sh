#!/usr/bin/env bash
set -e
echo "[INFO] Installing PostgreSQL client tools and PostGIS if possible."
OS="$(uname -s || true)"
if [ "$OS" = "Darwin" ]; then
  brew install postgresql@17 postgis
elif [ -f /etc/debian_version ]; then
  sudo apt-get update
  sudo apt-get install -y postgresql-client postgis
else
  echo "[WARN] Unsupported OS. Please install PostgreSQL client tools manually."
fi

# Ensure unversioned symlinks (pg_dump, pg_restore, psql) exist if only versioned binaries are present
BIN_DEST="/usr/local/bin"
if [ -d /opt/homebrew/bin ]; then
  BIN_DEST="/opt/homebrew/bin"
fi

link_if_exists() {
  local name="$1"; local ver="$2"
  local src
  if src=$(command -v "${name}-${ver}" 2>/dev/null); then
    echo "[INFO] Creating symlink for ${name} -> ${src}"
    ln -sf "$src" "${BIN_DEST}/${name}"
  else
    echo "[WARN] ${name}-${ver} not found; skipping symlink"
  fi
}

ensure_all_symlinks() {
  # Try to infer version from any available versioned binary
  local ver=""
  for probe in pg_dump psql pg_restore; do
    if ! command -v "$probe" >/dev/null 2>&1; then
      # Find first versioned variant in PATH
      for candidate in $(compgen -c | grep "^${probe}-[0-9][0-9]*$" | sort -r); do
        if command -v "$candidate" >/dev/null 2>&1; then
          ver="$(echo "$candidate" | sed -E 's/.*-([0-9]+)$/\1/')"
          break
        fi
      done
    fi
    [ -n "$ver" ] && break
  done

  if [ -z "$ver" ]; then
    echo "[INFO] No versioned PostgreSQL client binaries found that could inform symlinks."
    return 0
  fi

  # Create symlinks for all three if their versioned counterparts exist
  link_if_exists pg_dump "$ver"
  link_if_exists pg_restore "$ver"
  link_if_exists psql "$ver"
}

# Run the symlink ensure step
ensure_all_symlinks
