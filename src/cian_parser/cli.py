from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cian_parser.browser import (
    browser_context,
    collect_offer_urls_from_query,
    collect_offer_urls_from_search,
    fetch_offer_state,
    save_storage_state,
)
from cian_parser.config import CONFIG_DIR, SearchTarget, load_settings
from cian_parser.db import (
    connect,
    finish_run,
    init_schema,
    mark_queue,
    pending_urls,
    queue_urls,
    start_run,
    upsert_property,
)
from cian_parser.extract import canonicalize_url, is_offer_url, normalize_offer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse CIAN listings into PostgreSQL")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="Create tables in PostgreSQL")
    login = sub.add_parser("login", help="Open CIAN and save browser cookies outside the project")
    login.add_argument("--out", default=str(CONFIG_DIR / "cian_auth.json"))

    fetch = sub.add_parser("fetch", help="Queue and/or download listings")
    fetch.add_argument("targets", nargs="*", help="Offer URLs, search URLs, or search phrases")
    fetch.add_argument("--from-config", action="store_true", help="Also run searches from ~/.config/cian-parser/config.toml")
    fetch.add_argument("--queue-only", action="store_true", help="Collect URLs without opening offer pages")
    fetch.add_argument("--pending", action="store_true", help="Fetch queued URLs that are still pending")
    fetch.add_argument("--limit", type=int, default=None)

    args = parser.parse_args(argv)
    if args.command == "init-db":
        return cmd_init_db()
    if args.command == "login":
        return cmd_login(Path(args.out))
    if args.command == "fetch":
        return cmd_fetch(args)
    parser.error(f"Unknown command {args.command}")
    return 2


def cmd_init_db() -> int:
    settings = load_settings()
    with connect(settings.database_url) as conn:
        init_schema(conn)
    print("Database schema is ready.")
    return 0


def cmd_login(out: Path) -> int:
    settings = load_settings(require_db=False)
    print(f"A browser window will open. Log in to CIAN, then press Enter. Cookies go to {out}")
    with browser_context(settings, storage_path=None) as context:
        page = context.new_page()
        page.goto("https://www.cian.ru/", wait_until="domcontentloaded")
        input()
        save_storage_state(context, out)
    print(f"Saved session to {out}")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    settings = load_settings()
    targets = _collect_targets(args, settings)
    if not targets and not args.pending:
        print(
            "Pass a CIAN URL, a search phrase, --from-config, or --pending.",
            file=sys.stderr,
        )
        return 2
    with connect(settings.database_url) as conn:
        init_schema(conn)
        run_id = start_run(conn, notes="fetch")
        queued = 0
        saved = 0
        failed = 0
        try:
            with browser_context(settings) as context:
                page = context.new_page()
                offer_urls: list[str] = []
                if args.pending:
                    offer_urls.extend(pending_urls(conn, args.limit))
                for target in targets:
                    try:
                        found = _urls_for_target(page, target, settings)
                    except Exception as exc:
                        print(f"Search failed ({target}): {exc}", file=sys.stderr)
                        failed += 1
                        continue
                    queued += queue_urls(conn, found, source=target.query or target.url or "cli")
                    offer_urls.extend(found)
                    print(f"Queued {len(found)} listing URLs from {target.query or target.url}")

                unique = list(dict.fromkeys(canonicalize_url(url) for url in offer_urls if is_offer_url(url)))
                if args.limit:
                    unique = unique[: args.limit]
                if args.queue_only:
                    finish_run(conn, run_id, queued, saved, failed)
                    print(f"Done. queued={queued} saved={saved} failed={failed}")
                    return 0

                for url in unique:
                    try:
                        state = fetch_offer_state(page, url, settings)
                        row = normalize_offer(state, url=url)
                        upsert_property(conn, row)
                        mark_queue(conn, url, "done")
                        saved += 1
                        print(f"Saved {row['cian_id']} {row.get('address') or url}")
                    except Exception as exc:
                        mark_queue(conn, url, "failed", str(exc))
                        failed += 1
                        print(f"Failed {url}: {exc}", file=sys.stderr)
        finally:
            finish_run(conn, run_id, queued, saved, failed)
    print(f"Done. queued={queued} saved={saved} failed={failed}")
    return 0 if failed == 0 else 1


def _collect_targets(args: argparse.Namespace, settings) -> list[SearchTarget]:
    targets: list[SearchTarget] = []
    for raw in args.targets:
        if raw.startswith("http://") or raw.startswith("https://"):
            targets.append(SearchTarget(url=raw))
        else:
            targets.append(SearchTarget(query=raw))
    if args.from_config:
        targets.extend(settings.searches)
    return targets


def _urls_for_target(page, target: SearchTarget, settings) -> list[str]:
    if target.url and is_offer_url(target.url):
        return [canonicalize_url(target.url)]
    if target.url:
        return collect_offer_urls_from_search(page, target.url, settings)
    if target.query:
        return collect_offer_urls_from_query(page, target.query, settings)
    return []


if __name__ == "__main__":
    raise SystemExit(main())
