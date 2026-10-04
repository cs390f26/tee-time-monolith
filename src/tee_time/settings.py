"""Load .env and require the MySQL connection settings."""

import os

from dotenv import load_dotenv

REQUIRED_SETTINGS = (
    "MYSQL_HOST",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_DATABASE",
)
DEFAULT_PORT = "3306"


def ensure_settings() -> dict[str, str]:
    """Load .env (if present) and require the MySQL connection settings.

    MYSQL_PORT defaults to 3306 when it is omitted.

    Returns a dict of MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD,
    and MYSQL_DATABASE. If this returns, every required setting is set.

    Raises RuntimeError if any required setting is missing.
    """
    load_dotenv()
    missing = [name for name in REQUIRED_SETTINGS if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Missing required settings in the environment / .env: "
            + ", ".join(missing)
        )
    return {
        "MYSQL_HOST": os.environ["MYSQL_HOST"],
        "MYSQL_PORT": os.environ.get("MYSQL_PORT") or DEFAULT_PORT,
        "MYSQL_USER": os.environ["MYSQL_USER"],
        "MYSQL_PASSWORD": os.environ["MYSQL_PASSWORD"],
        "MYSQL_DATABASE": os.environ["MYSQL_DATABASE"],
    }
