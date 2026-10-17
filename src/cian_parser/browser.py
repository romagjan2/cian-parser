from __future__ import annotations

import random
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from playwright.sync_api import BrowserContext, Page, sync_playwright

from cian_parser.config import Settings
from cian_parser.extract import (
    canonicalize_url,
    extract_cian_config,
    is_offer_url,
    pick_offer_state,
    pick_serp_offers,
    urls_from_serp_offers,
)

EXTRACT_CONFIG_JS = """
() => {
  const cfg = window._cianConfig || {};
  const out = {};
  for (const [key, value] of Object.entries(cfg)) {
    out[key] = value;
  }
  return out;
}
"""


@contextmanager
def browser_context(settings: Settings, storage_path: Path | None = None) -> Iterator[BrowserContext]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=settings.headless)
        kwargs: dict[str, Any] = {
            "locale": "ru-RU",
            "user_agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        }
        state = storage_path or settings.storage_state
        if state and state.exists():
            kwargs["storage_state"] = str(state)
        context = browser.new_context(**kwargs)
        try:
            yield context
        finally:
            context.close()
            browser.close()


def wait_if_blocked(page: Page) -> None:
    content = page.content()
    if "cian_waf_block" in content or "подозрительный трафик" in content.lower():
        print("CIAN blocked the request. Solve it in the open browser, then press Enter.")
        input()
        page.reload(wait_until="domcontentloaded")


def _sleep(settings: Settings) -> None:
    jitter = settings.request_delay_seconds * 0.3
    time.sleep(max(0.4, random.uniform(settings.request_delay_seconds - jitter, settings.request_delay_seconds + jitter)))


def load_configs(page: Page, url: str, settings: Settings) -> dict[str, Any]:
    page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    wait_if_blocked(page)
    page.wait_for_timeout(800)
    configs = page.evaluate(EXTRACT_CONFIG_JS)
    if not configs:
        configs = extract_cian_config(page.content())
    _sleep(settings)
    return configs if isinstance(configs, dict) else {}


def collect_offer_urls_from_search(page: Page, start_url: str, settings: Settings) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    current = start_url
    for _ in range(settings.max_pages):
        configs = load_configs(page, current, settings)
        offers = pick_serp_offers(configs)
        page_urls = urls_from_serp_offers(offers)
        if not page_urls:
            page_urls = [
                canonicalize_url(href)
                for href in page.eval_on_selector_all(
                    '[data-testid="offer-card"] a[href], article a[href], [data-name="LinkArea"] a[href]',
                    "els => els.map(e => e.href)",
                )
                if href and is_offer_url(href)
            ]
        new_count = 0
        for url in page_urls:
            if url not in seen and is_offer_url(url):
                seen.add(url)
                urls.append(url)
                new_count += 1
        if new_count == 0:
            break
        next_url = _next_search_page(current)
        if next_url == current:
            clicked = _click_next(page)
            if not clicked:
                break
            current = page.url
        else:
            current = next_url
    return urls


def collect_offer_urls_from_query(page: Page, query: str, settings: Settings) -> list[str]:
    page.goto("https://www.cian.ru/", wait_until="domcontentloaded", timeout=90_000)
    wait_if_blocked(page)
    search = page.get_by_test_id("desktop-search-input")
    search.fill(query)
    page.wait_for_timeout(400)
    page.get_by_test_id("desktop-search-button").click()
    page.wait_for_timeout(1500)
    return collect_offer_urls_from_search(page, page.url, settings)


def fetch_offer_state(page: Page, url: str, settings: Settings) -> dict[str, Any]:
    configs = load_configs(page, url, settings)
    state = pick_offer_state(configs)
    if not state:
        raise RuntimeError(f"Could not extract offer JSON from {url}")
    return state


def save_storage_state(context: BrowserContext, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(path))


def _next_search_page(url: str) -> str:
    split = urlsplit(url)
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    page = int(query.get("p") or "1")
    query["p"] = str(page + 1)
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(query, doseq=True), split.fragment))


def _click_next(page: Page) -> bool:
    pagination = page.locator('[data-name="Pagination"] a')
    if pagination.count() == 0:
        return False
    try:
        pagination.last.click(timeout=5_000)
        page.wait_for_timeout(1000)
        return True
    except Exception:
        return False
