from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

OFFER_PATH_RE = re.compile(
    r"^/(sale|rent|snyat|kupit)/[a-z0-9-]+/\d+/?$",
    re.IGNORECASE,
)
OFFER_ID_RE = re.compile(
    r"cian\.ru/(?:sale|rent|snyat|kupit)/[a-z0-9-]+/(\d+)",
    re.IGNORECASE,
)
CONFIG_ASSIGN_RE = re.compile(
    r"window\._cianConfig(?:\['([^']+)'\]|\.([A-Za-z0-9_-]+))\s*=\s*"
)


def canonicalize_url(url: str) -> str:
    split = urlsplit(urljoin("https://www.cian.ru", url.strip()))
    path = split.path.rstrip("/") + ("/" if split.path.endswith("/") else "")
    if not path.endswith("/") and OFFER_PATH_RE.match(split.path.rstrip("/") + "/"):
        path = split.path.rstrip("/") + "/"
    clean = urlunsplit((split.scheme or "https", split.netloc, path or split.path, "", ""))
    return clean


def is_offer_url(url: str) -> bool:
    path = urlsplit(url).path
    return bool(OFFER_PATH_RE.match(path) or OFFER_PATH_RE.match(path.rstrip("/") + "/"))


def offer_id_from_url(url: str) -> int | None:
    match = OFFER_ID_RE.search(url)
    return int(match.group(1)) if match else None


def dig(data: Any, *path: str | int, default: Any = None) -> Any:
    current = data
    for key in path:
        if isinstance(key, int):
            if not isinstance(current, list) or key >= len(current) or key < -len(current):
                return default
            current = current[key]
        else:
            if not isinstance(current, dict) or key not in current:
                return default
            current = current[key]
    return current


def extract_cian_config(html: str) -> dict[str, Any]:
    """Parse window._cianConfig assignments from a CIAN HTML page."""
    configs: dict[str, Any] = {}
    decoder = json.JSONDecoder()
    for match in CONFIG_ASSIGN_RE.finditer(html):
        name = match.group(1) or match.group(2)
        try:
            payload, _ = decoder.raw_decode(html, match.end())
        except json.JSONDecodeError:
            continue
        configs[name] = payload
    return configs


def default_state(config_payload: Any) -> dict[str, Any] | None:
    if isinstance(config_payload, dict) and "offerData" in config_payload:
        return config_payload
    if not isinstance(config_payload, list):
        return None
    for item in config_payload:
        if isinstance(item, dict) and item.get("key") == "defaultState":
            value = item.get("value")
            return value if isinstance(value, dict) else None
    return None


def pick_offer_state(configs: dict[str, Any]) -> dict[str, Any] | None:
    preferred = (
        "frontend-offer-card",
        "frontend-offer-card-new",
        "frontend-new-offer-card",
    )
    for name in preferred:
        if name in configs:
            state = default_state(configs[name])
            if state:
                return state
    for payload in configs.values():
        state = default_state(payload)
        if state and (dig(state, "offerData", "offer") or dig(state, "offer")):
            return state
    return None


def pick_serp_offers(configs: dict[str, Any]) -> list[dict[str, Any]]:
    for payload in configs.values():
        state = default_state(payload)
        if not state:
            continue
        for path in (
            ("results", "offers"),
            ("offers"),
            ("searchState", "results", "offers"),
            ("data", "offersSerialized"),
        ):
            offers = dig(state, *path)
            if isinstance(offers, list) and offers:
                return [item for item in offers if isinstance(item, dict)]
    return []


def _to_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", ".").replace(" ", "")
    try:
        return float(text)
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    number = _to_number(value)
    return int(number) if number is not None else None


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 10_000_000_000:
            ts /= 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _join_address(geo: dict[str, Any]) -> str | None:
    user_input = geo.get("userInput")
    if user_input:
        return str(user_input)
    parts = []
    for item in geo.get("address") or []:
        if isinstance(item, dict) and item.get("title"):
            parts.append(str(item["title"]))
        elif isinstance(item, str):
            parts.append(item)
    return ", ".join(parts) if parts else None


def _address_component(geo: dict[str, Any], *types: str) -> str | None:
    for item in geo.get("address") or []:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or item.get("geoType") or "").lower()
        if item_type in {t.lower() for t in types}:
            return item.get("title") or item.get("fullName")
    return None


def _metro(geo: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for item in geo.get("undergrounds") or []:
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "name": item.get("name") or item.get("title"),
                "line_color": item.get("lineColor") or item.get("line_color"),
                "time": item.get("time"),
                "transport_type": item.get("transportType") or item.get("transport_type"),
            }
        )
    return result


def _photos(offer: dict[str, Any]) -> list[dict[str, Any]]:
    photos = []
    for photo in offer.get("photos") or offer.get("photosNew") or []:
        if not isinstance(photo, dict):
            continue
        photos.append(
            {
                "id": photo.get("id"),
                "full_url": photo.get("fullUrl") or photo.get("thumbnail2Url") or photo.get("url"),
                "mini_url": photo.get("thumbnailUrl") or photo.get("miniUrl"),
                "is_layout": photo.get("isLayout") or photo.get("isDefaultLayout"),
            }
        )
    return photos


def _phones(offer: dict[str, Any], seller: dict[str, Any]) -> list[str]:
    phones: list[str] = []
    for source in (
        offer.get("phones"),
        offer.get("phoneNumbers"),
        seller.get("phoneNumbers"),
        seller.get("phones"),
    ):
        for item in source or []:
            if isinstance(item, str):
                phones.append(item)
            elif isinstance(item, dict):
                number = item.get("number") or item.get("countryCode", "") + str(item.get("number") or "")
                if item.get("formattedNumber"):
                    number = item["formattedNumber"]
                if number:
                    phones.append(str(number))
    seen: set[str] = set()
    unique = []
    for phone in phones:
        if phone not in seen:
            seen.add(phone)
            unique.append(phone)
    return unique


def normalize_offer(state: dict[str, Any], url: str | None = None) -> dict[str, Any]:
    offer = dig(state, "offerData", "offer") or dig(state, "offer") or state
    if not isinstance(offer, dict):
        raise ValueError("Offer payload is missing")

    geo = offer.get("geo") if isinstance(offer.get("geo"), dict) else {}
    building = offer.get("building") if isinstance(offer.get("building"), dict) else {}
    land = offer.get("land") if isinstance(offer.get("land"), dict) else {}
    bargain = offer.get("bargainTerms") if isinstance(offer.get("bargainTerms"), dict) else {}
    seller = offer.get("user") if isinstance(offer.get("user"), dict) else {}
    coords = geo.get("coordinates") if isinstance(geo.get("coordinates"), dict) else {}

    cian_id = _to_int(offer.get("cianId") or offer.get("id") or offer_id_from_url(url or ""))
    full_url = offer.get("fullUrl") or offer.get("canonicalUrl") or url
    if full_url:
        full_url = canonicalize_url(str(full_url))

    moderation = offer.get("moderationInfo") if isinstance(offer.get("moderationInfo"), dict) else {}
    status = offer.get("status") or moderation.get("status")
    deadline = building.get("deadline") if isinstance(building.get("deadline"), dict) else {}
    year_built = _to_int(building.get("buildYear") or deadline.get("yearEnd"))
    owner = offer.get("fromHomeowner")
    if owner is None:
        owner = seller.get("isAgent") is False

    extras = {
        key: offer.get(key)
        for key in (
            "amenities",
            "furniture",
            "windowsViewType",
            "garage",
            "suburban",
            "newbuilding",
            "jkUrl",
            "category",
            "offerType",
            "dealType",
            "propertyType",
            "roomArea",
            "allRoomAreas",
            "combinedWcsCount",
            "separateWcsCount",
            "balconiesCount",
            "loggiasCount",
            "hasFurniture",
            "hasRamp",
            "isApartments",
            "isPenthouse",
            "isEuro",
            "isImported",
        )
        if key in offer
    }

    return {
        "cian_id": cian_id,
        "url": full_url,
        "deal_type": offer.get("dealType") or offer.get("offerType"),
        "category": offer.get("category") or offer.get("offerType"),
        "offer_type": offer.get("offerType"),
        "status": status,
        "title": offer.get("title") or offer.get("formattedTitle"),
        "description": offer.get("description"),
        "price": _to_int(bargain.get("price")),
        "price_rur": _to_int(bargain.get("priceRur") or bargain.get("price")),
        "currency": bargain.get("currency"),
        "price_type": bargain.get("priceType") or bargain.get("paymentPeriod"),
        "deposit": _to_int(bargain.get("deposit")),
        "total_area": _to_number(offer.get("totalArea")),
        "living_area": _to_number(offer.get("livingArea")),
        "kitchen_area": _to_number(offer.get("kitchenArea")),
        "land_area": _to_number(land.get("area")),
        "land_area_unit": land.get("areaUnitType"),
        "rooms": _to_int(offer.get("roomsCount")),
        "bedrooms": _to_int(offer.get("bedroomsCount")),
        "floor": _to_int(offer.get("floorNumber")),
        "floors_total": _to_int(building.get("floorsCount")),
        "year_built": year_built,
        "building_type": building.get("type") or building.get("houseMaterialType"),
        "material_type": building.get("materialType") or building.get("houseMaterialType"),
        "repair": offer.get("repairType"),
        "flat_type": offer.get("flatType"),
        "address": _join_address(geo),
        "region": _address_component(geo, "location", "okrug", "region"),
        "city": _address_component(geo, "location", "city", "raion"),
        "district": _address_component(geo, "raion", "district", "okrug"),
        "street": _address_component(geo, "street", "road"),
        "house": _address_component(geo, "house", "houseNumber"),
        "lat": _to_number(coords.get("lat")),
        "lng": _to_number(coords.get("lng")),
        "cadastral_number": offer.get("cadastralNumber") or land.get("cadastralNumber"),
        "seller_name": seller.get("agencyName") or seller.get("name") or seller.get("companyName"),
        "seller_type": seller.get("accountType") or seller.get("userType"),
        "agency_name": seller.get("agencyName") or seller.get("companyName"),
        "is_by_homeowner": bool(owner) if owner is not None else None,
        "published_at": _parse_dt(offer.get("creationDate") or offer.get("addedTimestamp") or offer.get("publicationDate")),
        "edited_at": _parse_dt(offer.get("editDate") or offer.get("updatedDate")),
        "metro": _metro(geo),
        "photos": _photos(offer),
        "phones": _phones(offer, seller),
        "features": extras,
        "building": building,
        "bargain_terms": bargain,
        "geo": geo,
        "seller": seller,
        "extras": extras,
        "raw": state,
    }


def urls_from_serp_offers(offers: list[dict[str, Any]]) -> list[str]:
    urls: list[str] = []
    for offer in offers:
        full = offer.get("fullUrl") or offer.get("url") or offer.get("canonical")
        if not full:
            cid = offer.get("cianId") or offer.get("id")
            category = offer.get("category") or "flat"
            deal = offer.get("dealType") or "sale"
            if cid:
                full = f"https://www.cian.ru/{deal}/{category}/{cid}/"
        if full:
            urls.append(canonicalize_url(str(full)))
    return urls
