import json
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

SITEMAP_URL = "https://www.spartantoyota.com/sitemap/"
OUTPUT_FILE = "inventory.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 Version/17.0 Mobile Safari/604.1"
    )
}


def clean_text(text):
    return " ".join(text.split())


def parse_vehicle_title(title):
    """
    Example:
    New 2026 Toyota RAV4 LE
    Used 2024 Toyota 4Runner TRD Pro
    """

    match = re.match(
        r"^(New|Used)\s+(\d{4})\s+([A-Za-z0-9\-]+)\s+(.+)$",
        title,
        re.IGNORECASE,
    )

    if not match:
        return None

    condition = match.group(1).title()
    year = int(match.group(2))
    make = match.group(3)
    remaining = match.group(4).strip()

    # Keep the full remaining name as model for now.
    # We can improve model/trim separation later.
    return {
        "condition": condition,
        "year": year,
        "make": make,
        "model": remaining,
        "trim": "",
    }


def get_vehicle_details(vehicle_url):
    """
    Attempts to pull price, VIN and a main image
    from the public Spartan Toyota vehicle page.
    """

    details = {
        "price": None,
        "mileage": None,
        "stock": "",
        "vin": "",
        "image": "",
    }

    try:
        response = requests.get(
            vehicle_url,
            headers=HEADERS,
            timeout=20,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        text = clean_text(soup.get_text(" ", strip=True))

        # VIN
        vin_match = re.search(
            r"\bVIN\s+([A-HJ-NPR-Z0-9]{17})\b",
            text,
            re.IGNORECASE,
        )

        if vin_match:
            details["vin"] = vin_match.group(1)

        # Try several common price labels
        price_patterns = [
            r"Germain Price\s*\$([\d,]+)",
            r"Advertised Price\s*\$([\d,]+)",
            r"Selling Price\s*\$([\d,]+)",
            r"Price\s*\$([\d,]+)",
        ]

        for pattern in price_patterns:
            match = re.search(pattern, text, re.IGNORECASE)

            if match:
                details["price"] = int(
                    match.group(1).replace(",", "")
                )
                break

        # Mileage on used vehicles
        mileage_patterns = [
            r"Mileage\s*([\d,]+)",
            r"([\d,]+)\s*Miles\b",
        ]

        for pattern in mileage_patterns:
            match = re.search(pattern, text, re.IGNORECASE)

            if match:
                try:
                    details["mileage"] = int(
                        match.group(1).replace(",", "")
                    )
                    break
                except ValueError:
                    pass

        # Stock number if published in page text
        stock_patterns = [
            r"Stock(?:\s*#|\s*Number)?\s*:?\s*([A-Za-z0-9\-]+)",
            r"Stock\s+([A-Za-z0-9\-]+)",
        ]

        for pattern in stock_patterns:
            match = re.search(pattern, text, re.IGNORECASE)

            if match:
                candidate = match.group(1)

                # Avoid accidentally capturing generic words
                if candidate.lower() not in {
                    "and",
                    "availability",
                    "vehicle",
                }:
                    details["stock"] = candidate
                    break

        # Main vehicle image
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")

            if not src:
                continue

            if (
                "dealereprocess" in src.lower()
                and "logo" not in src.lower()
            ):
                details["image"] = urljoin(vehicle_url, src)
                break

    except Exception as error:
        print(f"Could not read {vehicle_url}: {error}")

    return details


def get_inventory():
    response = requests.get(
        SITEMAP_URL,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    vehicles = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        title = clean_text(link.get_text(" ", strip=True))

        if not (
            title.startswith("New 20")
            or title.startswith("Used 20")
            or title.startswith("Used 19")
        ):
            continue

        parsed = parse_vehicle_title(title)

        if not parsed:
            continue

        vehicle_url = urljoin(
            SITEMAP_URL,
            link["href"],
        )

        # Only use individual Spartan Toyota vehicle pages
        if "/auto/" not in vehicle_url:
            continue

        if vehicle_url in seen_urls:
            continue

        seen_urls.add(vehicle_url)

        print(f"Reading: {title}")

        details = get_vehicle_details(vehicle_url)

        vehicle = {
            **parsed,
            **details,
            "source_url": vehicle_url,
            "contact": "#",
        }

        vehicles.append(vehicle)

    return vehicles


def main():
    vehicles = get_inventory()

    vehicles.sort(
        key=lambda vehicle: (
            vehicle["condition"] != "New",
            -vehicle["year"],
            vehicle["make"],
            vehicle["model"],
        )
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            vehicles,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print(
        f"Saved {len(vehicles)} vehicles "
        f"to {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
