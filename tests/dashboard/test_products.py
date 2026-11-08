from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from superbot.core import approvals
from superbot.research import finder  # noqa: F401  registers research.shortlist


def _propose(image_url: str, name: str = "Dog Bowl") -> int:
    return approvals.propose(
        "research.shortlist",
        f"Add to shortlist: {name}",
        {"product_id": 1, "image_url": image_url, "Product": name, "Sell price": "$19.99"},
    )


def test_approval_card_shows_https_image_and_hides_internal_keys(client):
    _propose("https://cf.cjdropshipping.com/P1.jpg")
    html = client.get("/").text
    assert '<img class="product" src="https://cf.cjdropshipping.com/P1.jpg" alt="Dog Bowl"' in html
    assert "product_id" not in html and "image_url" not in html
    assert "$19.99" in html


@pytest.mark.parametrize(
    "url", ["http://x.example/a.jpg", "javascript:alert(1)", "data:image/png;base64,AAA", ""]
)
def test_non_https_image_is_not_shown(client, url):
    _propose(url)
    assert "<img" not in client.get("/").text


def _shortlisted(engine, name: str, image_url: str = "https://cf.cjdropshipping.com/P1.jpg"):
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO products (cj_pid, name, image_url, cost_cents, ship_cents, ship_days,"
                " ship_method, sell_cents, profit_cents, score, reason, status, found_at)"
                " VALUES (:pid, :n, :img, 450, 320, 12, 'USPS+', 1999, 1141, 9, 'sells well',"
                " 'shortlisted', :t)"
            ),
            {"pid": name, "n": name, "img": image_url, "t": datetime.now(UTC).isoformat()},
        )


def test_products_page_lists_shortlisted_with_numbers(client, engine):
    _shortlisted(engine, "Dog Bowl")
    _shortlisted(engine, "Cat Brush")
    html = client.get("/products").text
    assert html.index("Cat Brush") < html.index("Dog Bowl")  # newest first
    for bit in ("$4.50", "$3.20 (USPS+, up to 12 days)", "$19.99", "$11.41", "9/10. sells well"):
        assert bit in html
    assert 'aria-current="page"' in html and ">Products</a>" in html


def test_products_page_escapes_names(client, engine):
    _shortlisted(engine, "<script>alert(1)</script>")
    html = client.get("/products").text
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_products_empty_state(client):
    assert "No products yet" in client.get("/products").text


def test_status_says_research_off_without_key(client):
    assert "Product research is off" in client.get("/status").text
