from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg.types.json import Jsonb

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"

UPSERT_SQL = """
INSERT INTO properties (
    cian_id, url, deal_type, category, offer_type, status, title, description,
    price, price_rur, currency, price_type, deposit,
    total_area, living_area, kitchen_area, land_area, land_area_unit,
    rooms, bedrooms, floor, floors_total, year_built, building_type, material_type,
    repair, flat_type, address, region, city, district, street, house,
    lat, lng, cadastral_number, seller_name, seller_type, agency_name, is_by_homeowner,
    published_at, edited_at, metro, photos, phones, features, building,
    bargain_terms, geo, seller, extras, raw, fetched_at
) VALUES (
    %(cian_id)s, %(url)s, %(deal_type)s, %(category)s, %(offer_type)s, %(status)s,
    %(title)s, %(description)s, %(price)s, %(price_rur)s, %(currency)s, %(price_type)s,
    %(deposit)s, %(total_area)s, %(living_area)s, %(kitchen_area)s, %(land_area)s,
    %(land_area_unit)s, %(rooms)s, %(bedrooms)s, %(floor)s, %(floors_total)s,
    %(year_built)s, %(building_type)s, %(material_type)s, %(repair)s, %(flat_type)s,
    %(address)s, %(region)s, %(city)s, %(district)s, %(street)s, %(house)s,
    %(lat)s, %(lng)s, %(cadastral_number)s, %(seller_name)s, %(seller_type)s,
    %(agency_name)s, %(is_by_homeowner)s, %(published_at)s, %(edited_at)s,
    %(metro)s, %(photos)s, %(phones)s, %(features)s, %(building)s,
    %(bargain_terms)s, %(geo)s, %(seller)s, %(extras)s, %(raw)s, now()
)
ON CONFLICT (cian_id) DO UPDATE SET
    url = EXCLUDED.url,
    deal_type = EXCLUDED.deal_type,
    category = EXCLUDED.category,
    offer_type = EXCLUDED.offer_type,
    status = EXCLUDED.status,
    title = EXCLUDED.title,
    description = EXCLUDED.description,
    price = EXCLUDED.price,
    price_rur = EXCLUDED.price_rur,
    currency = EXCLUDED.currency,
    price_type = EXCLUDED.price_type,
    deposit = EXCLUDED.deposit,
    total_area = EXCLUDED.total_area,
    living_area = EXCLUDED.living_area,
    kitchen_area = EXCLUDED.kitchen_area,
    land_area = EXCLUDED.land_area,
    land_area_unit = EXCLUDED.land_area_unit,
    rooms = EXCLUDED.rooms,
    bedrooms = EXCLUDED.bedrooms,
    floor = EXCLUDED.floor,
    floors_total = EXCLUDED.floors_total,
    year_built = EXCLUDED.year_built,
    building_type = EXCLUDED.building_type,
    material_type = EXCLUDED.material_type,
    repair = EXCLUDED.repair,
    flat_type = EXCLUDED.flat_type,
    address = EXCLUDED.address,
    region = EXCLUDED.region,
    city = EXCLUDED.city,
    district = EXCLUDED.district,
    street = EXCLUDED.street,
    house = EXCLUDED.house,
    lat = EXCLUDED.lat,
    lng = EXCLUDED.lng,
    cadastral_number = EXCLUDED.cadastral_number,
    seller_name = EXCLUDED.seller_name,
    seller_type = EXCLUDED.seller_type,
    agency_name = EXCLUDED.agency_name,
    is_by_homeowner = EXCLUDED.is_by_homeowner,
    published_at = EXCLUDED.published_at,
    edited_at = EXCLUDED.edited_at,
    metro = EXCLUDED.metro,
    photos = EXCLUDED.photos,
    phones = EXCLUDED.phones,
    features = EXCLUDED.features,
    building = EXCLUDED.building,
    bargain_terms = EXCLUDED.bargain_terms,
    geo = EXCLUDED.geo,
    seller = EXCLUDED.seller,
    extras = EXCLUDED.extras,
    raw = EXCLUDED.raw,
    fetched_at = now()
"""


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url)


def init_schema(conn: psycopg.Connection) -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def queue_urls(conn: psycopg.Connection, urls: Iterable[str], source: str) -> int:
    rows = [(url, source) for url in dict.fromkeys(urls)]
    if not rows:
        return 0
    inserted = 0
    with conn.cursor() as cur:
        for url, src in rows:
            cur.execute(
                """
                INSERT INTO listing_queue (url, source)
                VALUES (%s, %s)
                ON CONFLICT (url) DO NOTHING
                """,
                (url, src),
            )
            if cur.rowcount:
                inserted += 1
    conn.commit()
    return inserted


def pending_urls(conn: psycopg.Connection, limit: int | None = None) -> list[str]:
    sql = "SELECT url FROM listing_queue WHERE status = 'pending' ORDER BY created_at"
    if limit:
        sql += " LIMIT %s"
        params: tuple[Any, ...] = (limit,)
    else:
        params = ()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [row[0] for row in cur.fetchall()]


def mark_queue(conn: psycopg.Connection, url: str, status: str, error: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE listing_queue
            SET status = %s, error = %s, fetched_at = now()
            WHERE url = %s
            """,
            (status, error, url),
        )
    conn.commit()


def _json_params(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    for key in (
        "metro",
        "photos",
        "phones",
        "features",
        "building",
        "bargain_terms",
        "geo",
        "seller",
        "extras",
        "raw",
    ):
        payload[key] = Jsonb(payload.get(key) or ({} if key != "phones" and key != "metro" and key != "photos" else []))
    return payload


def upsert_property(conn: psycopg.Connection, row: dict[str, Any]) -> None:
    if not row.get("cian_id"):
        raise ValueError("cian_id is required")
    with conn.cursor() as cur:
        cur.execute(UPSERT_SQL, _json_params(row))
    conn.commit()


def start_run(conn: psycopg.Connection, notes: str | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO scrape_runs (notes) VALUES (%s) RETURNING id", (notes,))
        run_id = cur.fetchone()[0]
    conn.commit()
    return int(run_id)


def finish_run(conn: psycopg.Connection, run_id: int, queued: int, saved: int, failed: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE scrape_runs
            SET finished_at = now(), queued = %s, saved = %s, failed = %s
            WHERE id = %s
            """,
            (queued, saved, failed, run_id),
        )
    conn.commit()
