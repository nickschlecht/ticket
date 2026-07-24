import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

import resend
from playwright.sync_api import sync_playwright


ROOT_DIR = Path(__file__).resolve().parent


def load_env_file(path: Optional[Path] = None) -> None:
    env_path = path or ROOT_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()
PRICE_FILE = Path(os.environ.get("PRICE_FILE", str(ROOT_DIR / "prices.json")))
LOG_FILE = Path(os.environ.get("LOG_FILE", str(ROOT_DIR / "tracker.log")))

PRICE_LIMITS = {
    "7": 2000,
    "8": 2000,
    "9": 2000,
    "23": 2000,
    "24": 2000,
    "25": 2000,
    "105": 1200,
    "106": 1200,
    "107": 1200,
    "108": 1200,
    "109": 1200,
    "110": 1200,
    "111": 1200,
    "128": 1200,
    "127": 1200,
    "126": 1200,
    "125": 1200,
    "124": 1200,
    "123": 1200,
    "122": 1200,
    "121": 1200,
}


def get_limit(section_key: str) -> Optional[float]:
    return PRICE_LIMITS.get(section_key)

def get_markets() -> Dict[str, Dict[str, object]]:
    return {
        "ticketmaster": {
            "url": os.environ.get("TICKETMASTER_URL", "PUT_TICKET_URL_HERE"),
            "section_selectors": [".ticket-section .section", ".section", "[data-testid='section-name']"],
            "price_selectors": [".ticket-section .price", ".price", "[data-testid='price']"],
        },
        "stubhub": {
            "url": os.environ.get("STUBHUB_URL", "PUT_TICKET_URL_HERE"),
            "section_selectors": [".ticket-section .section", ".section", "[data-testid='section-name']"],
            "price_selectors": [".ticket-section .price", ".price", "[data-testid='price']"],
        },
        "seatgeek": {
            "url": os.environ.get("SEATGEEK_URL", "PUT_TICKET_URL_HERE"),
            "section_selectors": [".ticket-section .section", ".section", "[data-testid='section-name']"],
            "price_selectors": [".ticket-section .price", ".price", "[data-testid='price']"],
        },
    }


MARKETS = get_markets()


def normalize_price(value: object) -> float:
    text = str(value or "").strip()
    match = re.search(r"(\d+(?:,\d{3})*(?:\.\d+)?)", text)
    if not match:
        raise ValueError(f"Could not find a price in: {value}")
    return float(match.group(1).replace(",", ""))


def normalize_section(value: object) -> str:
    text = str(value or "")
    match = re.search(r"(\d+)", text)
    return match.group(1) if match else ""


def should_alert(price: float, limit: float, previous_price: Optional[float]) -> bool:
    if price > limit:
        return False
    if previous_price is None:
        return True
    return price < previous_price


def load_state() -> Dict[str, Any]:
    try:
        with PRICE_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {"last_seen": {}, "summary": {}, "last_summary_sent": None}
    except json.JSONDecodeError:
        return {"last_seen": {}, "summary": {}, "last_summary_sent": None}

    if isinstance(data, dict) and "last_seen" in data:
        return {
            "last_seen": data.get("last_seen", {}),
            "summary": data.get("summary", {}),
            "last_summary_sent": data.get("last_summary_sent"),
        }

    return {"last_seen": data, "summary": {}, "last_summary_sent": None}


def save_state(state: Dict[str, Any]) -> None:
    PRICE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PRICE_FILE.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=4)


def log_message(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"{date.today().isoformat()} {message}\n")


def send_email(subject: str, html: str) -> bool:
    api_key = os.environ.get("RESEND_API_KEY")
    to_email = os.environ.get("EMAIL_ADDRESS") or os.environ.get("EMAIL")

    if not api_key or not to_email:
        print("Skipping email because RESEND_API_KEY or EMAIL_ADDRESS is not configured.")
        return False

    resend.api_key = api_key
    resend.Emails.send(
        {
            "from": os.environ.get("EMAIL_FROM", "alerts@yourdomain.com"),
            "to": [to_email],
            "subject": subject,
            "html": html,
        }
    )
    return True


def send_threshold_alert(section: str, price: float, marketplace: str, url: str) -> None:
    html = f"""
    <h2>Threshold hit!</h2>
    <p>
    Marketplace: {marketplace}<br>
    Section: {section}<br>
    Price: ${price:.2f}
    </p>
    <p>
    Buy Now:<br>
    {url}
    </p>
    """
    send_email("LoL Worlds Ticket Threshold Alert", html)


def update_summary(state: Dict[str, Any], section_key: str, price: float) -> None:
    summary = state.setdefault("summary", {})
    section_summary = summary.setdefault(section_key, {"high": None, "low": None})

    current_high = section_summary.get("high")
    current_low = section_summary.get("low")

    if current_high is None or price > current_high:
        section_summary["high"] = price
    if current_low is None or price < current_low:
        section_summary["low"] = price


def send_daily_summary(state: Dict[str, Any]) -> None:
    today = date.today().isoformat()
    if state.get("last_summary_sent") == today:
        return

    summary = state.get("summary", {})
    if not summary:
        return

    rows = []
    for section_key in sorted(summary):
        section_summary = summary[section_key]
        high = section_summary.get("high")
        low = section_summary.get("low")
        if high is None or low is None:
            continue
        rows.append(
            f"<tr><td>{section_key}</td><td>${high:.2f}</td><td>${low:.2f}</td></tr>"
        )

    if not rows:
        return

    html = f"""
    <h2>LoL Worlds Ticket Daily Summary</h2>
    <p>Highest and lowest seen prices for each section.</p>
    <table>
      <thead>
        <tr><th>Section</th><th>Highest Seen</th><th>Lowest Seen</th></tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
    """
    if send_email("LoL Worlds Ticket Daily Summary", html):
        state["last_summary_sent"] = today


def scrape_tickets(marketplace: str, config: Dict[str, list]) -> Dict[str, float]:
    url = config.get("url", "")
    if not url or "PUT_TICKET_URL_HERE" in url:
        print(f"Skipping {marketplace}: no URL configured.")
        return {}

    tickets: Dict[str, float] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        for section_selector in config.get("section_selectors", []):
            for price_selector in config.get("price_selectors", []):
                try:
                    sections = page.locator(section_selector)
                    prices = page.locator(price_selector)
                    count = min(sections.count(), prices.count())

                    for index in range(count):
                        section_text = sections.nth(index).inner_text().strip()
                        price_text = prices.nth(index).inner_text().strip()
                        if not section_text or not price_text:
                            continue
                        price = normalize_price(price_text)
                        tickets[section_text] = price

                    if tickets:
                        browser.close()
                        return tickets
                except Exception as exc:
                    print(f"Selector mismatch for {marketplace}: {exc}")
                    continue

        browser.close()

    return tickets


def check_prices() -> None:
    state = load_state()
    last_seen = state.get("last_seen", {})
    new_last_seen: Dict[str, float] = {}

    for marketplace, config in MARKETS.items():
        scraped_tickets = scrape_tickets(marketplace, config)
        if not scraped_tickets:
            continue

        for section, price in scraped_tickets.items():
            section_key = normalize_section(section)
            if not section_key:
                continue

            full_key = f"{marketplace}:{section_key}"
            new_last_seen[full_key] = price
            update_summary(state, section_key, price)

            previous_price = last_seen.get(full_key)
            limit = get_limit(section_key)
            if limit is not None and should_alert(price, limit, previous_price):
                send_threshold_alert(section_key, price, marketplace, config.get("url", ""))

    state["last_seen"] = new_last_seen
    send_daily_summary(state)
    save_state(state)


def main() -> None:
    try:
        check_prices()
        print("Price check completed.")
        log_message("Price check completed.")
    except Exception as exc:
        print(f"Tracking run failed: {exc}")
        log_message(f"Tracking run failed: {exc}")
        raise


if __name__ == "__main__":
    main()