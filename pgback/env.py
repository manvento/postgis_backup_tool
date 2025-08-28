import os, socket
from urllib.parse import urlparse, parse_qs


class ConfigError(RuntimeError):
    pass


def get_env():
    url = os.getenv("JDBC_URL")
    user = os.getenv("JDBC_USER")
    pwd = os.getenv("JDBC_PASSWORD")
    if not url or not user or pwd is None:
        raise ConfigError("Missing required env vars: JDBC_URL, JDBC_USER, JDBC_PASSWORD")
    return {"jdbc_url": url.strip("'").strip('"'), "user": user, "password": pwd}


def parse_jdbc_postgres(jdbc_url: str):
    if not jdbc_url.startswith("jdbc:postgresql://"):
        raise ConfigError("JDBC_URL must start with jdbc:postgresql://")
    raw = jdbc_url[len("jdbc:"):]
    u = urlparse(raw)
    host = u.hostname or "localhost"
    port = u.port or 5432
    db = u.path.lstrip("/") or "postgres"
    q = parse_qs(u.query or "")
    current_schema = None
    if "currentSchema" in q and q["currentSchema"]:
        current_schema = q["currentSchema"][0]
    return {
        "host": host,
        "port": int(port),
        "database": db,
        "current_schema": current_schema,
    }


def build_pg_uri(user: str, password: str, host: str, port: int, database: str) -> str:
    from urllib.parse import quote
    return f"postgresql://{quote(user)}:{quote(password)}@{host}:{port}/{database}"


def resolve_pg_from_env():
    """
    Returns a dict with:
      - uri: postgresql://user:pass@host:port/db
      - schema: value of currentSchema (or None)
      - jdbc_url: original JDBC URL
      - host: hostname
      - port: port (int)
      - database: db name
    """
    env = get_env()
    parsed = parse_jdbc_postgres(env["jdbc_url"])
    uri = build_pg_uri(env["user"], env["password"], parsed["host"], parsed["port"], parsed["database"])
    return {
        "uri": uri,
        "schema": parsed["current_schema"],
        "jdbc_url": env["jdbc_url"],
        "host": parsed["host"],
        "port": parsed["port"],
        "database": parsed["database"],
    }


def host_is_resolvable(host: str) -> bool:
    try:
        socket.gethostbyname(host)
        return True
    except socket.gaierror:
        return False
