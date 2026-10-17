# cian-parser

Python parser that opens CIAN listing and search pages, extracts the full in-page offer JSON (`window._cianConfig`), and upserts it into PostgreSQL.

Indexed columns cover price, area, geo, seller, photos, metro, and building fields. The complete payload is also stored in `properties.raw` (JSONB).

Credentials and search lists live **outside** this repo, in `~/.config/cian-parser/`.

## Setup

```bash
cd ~/cian-parser
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
```

Copy the examples out of the project:

```bash
mkdir -p ~/.config/cian-parser
cp env.example ~/.config/cian-parser/.env
cp config.example.toml ~/.config/cian-parser/config.toml
# edit DATABASE_URL, POSTGRES_* and searches
```

Start Postgres (port **5433** by default so it does not collide with an existing local server):

```bash
docker compose --env-file ~/.config/cian-parser/.env up -d
```

Or point `DATABASE_URL` at a database you already run.

```bash
cian-parser init-db
```

Optional: save a logged-in CIAN session (cookies are written outside the repo):

```bash
cian-parser login
```

## Usage

Search URL, free-text query, or a direct offer URL:

```bash
cian-parser fetch "https://www.cian.ru/sale/flat/222059642/"
cian-parser fetch "https://www.cian.ru/cat.php?deal_type=sale&offer_type=suburban&engine_version=2&region=1"
cian-parser fetch "Купить земельный участок в селе Чемал республики Алтай"
cian-parser fetch --from-config
cian-parser fetch --queue-only --from-config
cian-parser fetch --pending
```

CIAN may show a WAF interstitial. The browser stays visible by default (`HEADLESS=false`); complete the check in the window and press Enter if the parser asks.

## Schema

- `listing_queue` — discovered offer URLs
- `properties` — one row per `cian_id`, including `raw` JSONB
- `scrape_runs` — fetch stats
