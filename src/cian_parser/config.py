from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

try:
    import tomllib
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


CONFIG_DIR = Path.home() / ".config" / "cian-parser"
ENV_PATH = CONFIG_DIR / ".env"
TOML_PATH = CONFIG_DIR / "config.toml"


@dataclass(frozen=True)
class SearchTarget:
    url: str | None = None
    query: str | None = None


@dataclass
class Settings:
    database_url: str
    storage_state: Path | None
    headless: bool = False
    request_delay_seconds: float = 2.0
    max_pages: int = 40
    searches: list[SearchTarget] = field(default_factory=list)


def load_settings(*, require_db: bool = True) -> Settings:
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    else:
        load_dotenv()

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if require_db and not database_url:
        raise RuntimeError(
            f"DATABASE_URL is not set. Put it in {ENV_PATH} (outside the project)."
        )

    storage = os.environ.get("PLAYWRIGHT_STORAGE_STATE", "").strip()
    storage_path = Path(storage).expanduser() if storage else CONFIG_DIR / "cian_auth.json"
    if not storage_path.exists():
        storage_path = None

    toml_data: dict = {}
    if TOML_PATH.exists():
        with TOML_PATH.open("rb") as fh:
            toml_data = tomllib.load(fh)

    searches: list[SearchTarget] = []
    for item in toml_data.get("searches") or []:
        searches.append(
            SearchTarget(
                url=(item.get("url") or None),
                query=(item.get("query") or None),
            )
        )

    return Settings(
        database_url=database_url,
        storage_state=storage_path,
        headless=_bool(os.environ.get("HEADLESS", toml_data.get("headless", False))),
        request_delay_seconds=float(
            os.environ.get(
                "REQUEST_DELAY_SECONDS",
                toml_data.get("request_delay_seconds", 2.0),
            )
        ),
        max_pages=int(os.environ.get("MAX_PAGES", toml_data.get("max_pages", 40))),
        searches=searches,
    )


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
