from pathlib import Path

from cian_parser.extract import (
    extract_cian_config,
    is_offer_url,
    normalize_offer,
    pick_offer_state,
)

FIXTURE = Path(__file__).parent / "fixtures" / "offer_state.json"


def test_is_offer_url() -> None:
    assert is_offer_url("https://www.cian.ru/sale/flat/222059642/")
    assert is_offer_url("https://www.cian.ru/sale/suburban/123")
    assert not is_offer_url("https://www.cian.ru/cat.php?deal_type=sale")


def test_normalize_offer_fixture() -> None:
    import json

    state = json.loads(FIXTURE.read_text(encoding="utf-8"))
    row = normalize_offer(state)
    assert row["cian_id"] == 222059642
    assert row["price_rur"] == 12500000
    assert row["rooms"] == 2
    assert row["total_area"] == 54.2
    assert row["city"] == "Москва"
    assert row["photos"][0]["full_url"].endswith("1.jpg")
    assert row["phones"] == ["+7 999 000-00-00"]
    assert row["raw"]["offerData"]["offer"]["cianId"] == 222059642


def test_extract_from_html() -> None:
    html = """
    <script>
    window._cianConfig['frontend-offer-card'] = [{"key": "defaultState", "value": {"offerData": {"offer": {"cianId": 1}}}}];
    </script>
    """
    configs = extract_cian_config(html)
    state = pick_offer_state(configs)
    assert state is not None
    assert state["offerData"]["offer"]["cianId"] == 1
