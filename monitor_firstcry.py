# monitor_firstcry.py
# Final FirstCry monitor — email notifications (env/.env friendly)
# Usage:
# 1. Create a .env with your settings (example below).
# 2. Run: python monitor_firstcry.py
#
# Example .env:
# SEARCH_QUERY=hot wheels
# # or a full FirstCry category URL:
# # SEARCH_QUERY=https://www.firstcry.com/hotwheels/5/0/113?sort=popularity...
# FIRSTCRY_SEARCH_URL=https://www.firstcry.com/search?query=
# SMTP_HOST=smtp.gmail.com
# SMTP_PORT=587
# SMTP_USER=patel.harshaprakash@gmail.com
# SMTP_PASS=your_16_char_app_password_here
# EMAIL_TO=harshaprakashpatel5230@gmail.com
# SHOW_SAMPLE=1

import os
import time
import sqlite3
from urllib.parse import quote_plus, urlparse
import requests
from bs4 import BeautifulSoup
from email.message import EmailMessage
import smtplib

# Optional .env loader
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ---------- Configuration (from env/.env) ----------
SEARCH_QUERY = os.getenv("SEARCH_QUERY", "hot wheels").strip()
FIRSTCRY_SEARCH_URL = os.getenv("FIRSTCRY_SEARCH_URL", "https://www.firstcry.com/search?query=")
DB_PATH = os.getenv("DB_PATH", "firstcry_monitor.db")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_TO = os.getenv("EMAIL_TO", SMTP_USER)

# If SHOW_SAMPLE is set to "1", prints first 10 parsed products for inspection
SHOW_SAMPLE = os.getenv("SHOW_SAMPLE", "0") == "1"

HEADERS = {
    "User-Agent": os.getenv("USER_AGENT", "FirstCryMonitor/1.0 (contact: your_email@example.com)")
}
# ---------------------------------------------------

def requests_get_with_retry(url, headers=None, timeout=20, retries=2, backoff=2):
    last_exc = None
    for attempt in range(1, retries + 2):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            last_exc = e
            if attempt <= retries:
                wait = backoff * attempt
                print(f"Request failed (attempt {attempt}) — retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise last_exc

def ensure_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            title TEXT,
            last_seen INTEGER
        )
    """)
    conn.commit()
    return conn

def build_fetch_url(query):
    if query.lower().startswith("http://") or query.lower().startswith("https://"):
        return query
    return FIRSTCRY_SEARCH_URL + quote_plus(query)

def fetch_search_html(query):
    url = build_fetch_url(query)
    print("Fetching URL:", url)
    r = requests_get_with_retry(url, headers=HEADERS)
    return r.text

def parse_products_from_html(html_text):
    """
    Tuned parser:
      - Primary: links containing '/hotwheels/' (category pages)
      - Secondary: links containing '/product/'
      - Tertiary: data-product-id attributes
      - Final fallback: meaningful <a> text with path segments
    Returns list of (product_id, title)
    """
    soup = BeautifulSoup(html_text, "html.parser")
    products = []

    # Primary: '/hotwheels/' links
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(strip=True)
        if not text:
            continue
        if "/hotwheels/" in href:
            parsed = urlparse(href)
            path = parsed.path
            parts = [p for p in path.split("/") if p]
            pid = parts[-1] if parts else path
            title = " ".join(text.split())
            products.append((pid, title))

    # Secondary: '/product/' links
    if not products:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(strip=True)
            if not text:
                continue
            if "/product/" in href:
                parsed = urlparse(href)
                path = parsed.path
                parts = [p for p in path.split("/") if p]
                pid = parts[-1] if parts else path
                title = " ".join(text.split())
                products.append((pid, title))

    # Tertiary: data-product-id attributes
    if not products:
        for tile in soup.select("[data-product-id]"):
            pid = tile.get("data-product-id")
            title_tag = tile.select_one("a") or tile.select_one(".product-name") or tile.select_one("h2") or tile.select_one("h3")
            title = title_tag.get_text(strip=True) if title_tag else ""
            if pid:
                products.append((pid.strip(), title.strip()))

    # Final fallback: any <a> with visible text (avoid tiny labels)
    if not products:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            text = a.get_text(strip=True)
            if not text or len(text) < 4:
                continue
            if "javascript" in href.lower():
                continue
            pid = urlparse(href).path.split("/")[-1].split("?")[0] or href
            products.append((pid, text))

    # Deduplicate preserving first seen title
    unique = {}
    for pid, title in products:
        if pid and pid not in unique:
            unique[pid] = title

    return [(pid, unique[pid]) for pid in unique]

def send_email(subject, body):
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS or not EMAIL_TO:
        print("Email not configured properly. Skipping email send.")
        print("Subject:", subject)
        return
    msg = EmailMessage()
    msg["From"] = SMTP_USER
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.ehlo()
        if SMTP_PORT == 587:
            s.starttls()
            s.ehlo()
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
    print("Email sent:", subject)

def main():
    try:
        print("="*40)
        print(f"FirstCry Monitor — query: '{SEARCH_QUERY}'")
        conn = ensure_db()
        c = conn.cursor()

        html_text = fetch_search_html(SEARCH_QUERY)
        if not html_text or len(html_text) < 100:
            raise RuntimeError("Fetched HTML is suspiciously small — possible blocking or incorrect URL.")

        products = parse_products_from_html(html_text)

        if SHOW_SAMPLE:
            print("First 10 parsed products (sample):")
            for i, (pid, title) in enumerate(products[:10], start=1):
                print(f"{i}. {title} — id: {pid}")

        now = int(time.time())
        c.execute("SELECT COUNT(*) FROM products")
        prev_count = c.fetchone()[0]

        new_found = []
        for pid, title in products:
            c.execute("SELECT product_id FROM products WHERE product_id = ?", (pid,))
            if c.fetchone() is None:
                c.execute("INSERT OR REPLACE INTO products (product_id, title, last_seen) VALUES (?, ?, ?)",
                          (pid, title, now))
                new_found.append((pid, title))
            else:
                c.execute("UPDATE products SET last_seen = ? WHERE product_id = ?", (now, pid))
        conn.commit()
        curr_count = len(products)

        print(f"Parsed products: {curr_count} (previous stored: {prev_count})")

        if new_found:
            lines = [f"New items found for '{SEARCH_QUERY}' on FirstCry ({len(new_found)}):"]
            for pid, title in new_found:
                lines.append(f"• {title} — id: {pid}")
            body = "\n".join(lines)
            send_email(f"[FirstCry] New items for {SEARCH_QUERY}", body)
        elif curr_count > prev_count:
            send_email(f"[FirstCry] Count increased for {SEARCH_QUERY}", f"Count: {prev_count} → {curr_count}")
        else:
            print("No new items found this run.")

        print("Run complete.")
    except Exception as e:
        print("Error:", repr(e))
        try:
            send_email(f"[FirstCry Monitor] Error for {SEARCH_QUERY}", repr(e))
        except Exception:
            pass

if __name__ == "__main__":
    main()
