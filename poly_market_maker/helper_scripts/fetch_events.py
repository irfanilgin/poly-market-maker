import requests
import csv
import time
from datetime import datetime, timezone
from logger import logger  # <--- Import our new logger

# --- CONFIGURATION ---
API_URL = "https://gamma-api.polymarket.com/events"
OUTPUT_FILE = "all_events.csv"
MIN_LIQUIDITY = 5000  # Skip tiny markets
MAX_EVENTS_TO_FETCH = 5000  # Safety limit


def fetch_all_events():
    logger.info(f"🚜 Starting Event Harvest... (Min Liq: ${MIN_LIQUIDITY:,.0f})")

    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    all_rows = []
    offset = 0
    limit = 100

    # Get current UTC time to filter out old 'zombie' markets
    now_utc = datetime.now(timezone.utc)

    while offset < MAX_EVENTS_TO_FETCH:
        params = {
            "closed": "false",  # Only active events
            "limit": limit,
            "offset": offset
        }

        try:
            response = requests.get(API_URL, params=params, headers=headers)

            if response.status_code != 200:
                logger.error(f"API Error {response.status_code}: {response.text}")
                # If API is overwhelmed (429) or invalid (422), stop.
                break

            data = response.json()
            if not data:
                logger.info("✅ End of list reached.")
                break

        except Exception as e:
            logger.error(f"Connection Failed: {e}")
            break

        # Process this batch of events
        for event in data:
            # 1. DATE CHECK (The Zombie Filter)
            # If endDate is in the past, skip it, even if API says "active"
            end_date_str = event.get('endDate')
            if end_date_str:
                try:
                    # ISO Format fix: 2024-11-05T00:00:00Z -> replace Z with +00:00
                    market_end = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
                    if market_end < now_utc:
                        continue
                except ValueError:
                    continue  # Skip if date is broken

            # 2. MARKET PROCESSING
            # An event is a container. We look at the markets inside it.
            markets = event.get('markets', [])
            for m in markets:
                liq = float(m.get('liquidity', 0) or 0)

                if liq >= MIN_LIQUIDITY:
                    # Create a clean title: "Event Title - Market Question"
                    full_title = f"{event.get('title')} - {m.get('question')}"
                    full_title = full_title.replace('\n', ' ').strip()

                    row = {
                        "Event_ID": event.get('id'),
                        "Market_ID": m.get('conditionId'),  # Crucial for trading
                        "Title": full_title,
                        "Liquidity": liq,
                        "Volume": m.get('volume'),
                        "End_Date": end_date_str
                    }
                    all_rows.append(row)

        offset += limit
        logger.info(f"   Scanned {offset} events | Collected {len(all_rows)} valid markets...")
        time.sleep(0.1)  # Be polite to API

    return all_rows


def save_to_csv(data):
    if not data:
        logger.warning("No markets found to save.")
        return

    keys = ["Event_ID", "Market_ID", "Title", "Liquidity", "Volume", "End_Date"]

    try:
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)
        logger.info(f"💾 Successfully saved {len(data)} markets to {OUTPUT_FILE}")
    except Exception as e:
        logger.error(f"Failed to save CSV: {e}")


if __name__ == "__main__":
    data = fetch_all_events()
    save_to_csv(data)