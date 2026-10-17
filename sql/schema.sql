CREATE TABLE IF NOT EXISTS listing_queue (
    url TEXT PRIMARY KEY,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    fetched_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS properties (
    cian_id BIGINT PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    deal_type TEXT,
    category TEXT,
    offer_type TEXT,
    status TEXT,
    title TEXT,
    description TEXT,
    price BIGINT,
    price_rur BIGINT,
    currency TEXT,
    price_type TEXT,
    deposit BIGINT,
    total_area NUMERIC,
    living_area NUMERIC,
    kitchen_area NUMERIC,
    land_area NUMERIC,
    land_area_unit TEXT,
    rooms INTEGER,
    bedrooms INTEGER,
    floor INTEGER,
    floors_total INTEGER,
    year_built INTEGER,
    building_type TEXT,
    material_type TEXT,
    repair TEXT,
    flat_type TEXT,
    address TEXT,
    region TEXT,
    city TEXT,
    district TEXT,
    street TEXT,
    house TEXT,
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    cadastral_number TEXT,
    seller_name TEXT,
    seller_type TEXT,
    agency_name TEXT,
    is_by_homeowner BOOLEAN,
    published_at TIMESTAMPTZ,
    edited_at TIMESTAMPTZ,
    metro JSONB NOT NULL DEFAULT '[]'::jsonb,
    photos JSONB NOT NULL DEFAULT '[]'::jsonb,
    phones JSONB NOT NULL DEFAULT '[]'::jsonb,
    features JSONB NOT NULL DEFAULT '{}'::jsonb,
    building JSONB NOT NULL DEFAULT '{}'::jsonb,
    bargain_terms JSONB NOT NULL DEFAULT '{}'::jsonb,
    geo JSONB NOT NULL DEFAULT '{}'::jsonb,
    seller JSONB NOT NULL DEFAULT '{}'::jsonb,
    extras JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS properties_deal_type_idx ON properties (deal_type);
CREATE INDEX IF NOT EXISTS properties_category_idx ON properties (category);
CREATE INDEX IF NOT EXISTS properties_city_idx ON properties (city);
CREATE INDEX IF NOT EXISTS properties_price_rur_idx ON properties (price_rur);
CREATE INDEX IF NOT EXISTS properties_raw_gin ON properties USING GIN (raw);
CREATE INDEX IF NOT EXISTS properties_fetched_at_idx ON properties (fetched_at DESC);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    queued INTEGER NOT NULL DEFAULT 0,
    saved INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);
