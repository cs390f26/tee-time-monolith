"""Load .env and require the SQLite database path."""

import os

from dotenv import load_dotenv

REQUIRED_SETTINGS = ("DATABASE_PATH",)


def ensure_settings() -> dict[str, str]:
    """Load .env (if present) and require DATABASE_PATH.

    Returns a dict of the required values. If this returns, every key in
    REQUIRED_SETTINGS is set in the environment (and in the returned dict).

    Raises RuntimeError if any required setting is missing.
    """
    load_dotenv()
    missing = [name for name in REQUIRED_SETTINGS if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Missing required settings in the environment / .env: "
            + ", ".join(missing)
        )
    return {name: os.environ[name] for name in REQUIRED_SETTINGS}
