import json
import os
import re
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

BERLIN = ZoneInfo("Europe/Berlin")
TARGET_HOURS = {10, 13, 17}  # Uhrzeiten (Berliner Zeit), zu denen wirklich geprüft wird

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Reihenfolge für die Sortierung der Ergebnis-Tabelle
STATUS_PRIORITY = {
    "verfügbar": 0,
    "nicht verfügbar": 1,
    "unbekannt": 2,
}


def load_urls(path="urls.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_status(path="status.json"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_status(data, path="status.json"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def check_url(url, browser):
    try:
        page = browser.new_page(user_agent=USER_AGENT)
        page.goto(url, timeout=45000, wait_until="load")

        # Manche Bibliotheksseiten haben einen JS-Bot-Schutz, der die Seite nach
        # einem kurzen Skript per document.location.reload() neu lädt.
        # Daher: kurz warten und erneut auf Netzwerk-Ruhe warten.
        page.wait_for_timeout(3000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        text = page.inner_text("body")
        page.close()

        text_lower = text.lower()
        if "nicht verfügbar" in text_lower:
            status = "nicht verfügbar"
        elif "verfügbar" in text_lower:
            status = "verfügbar"
        else:
            status = "unbekannt"

        return_date = None
        match = re.search(
            r"rückgabedatum\D{0,20}(\d{1,2}\.\d{1,2}\.\d{2,4})",
            text,
            re.IGNORECASE,
        )
        if match:
            return_date = match.group(1)

        return status, return_date
    except Exception as e:
        return f"fehler: {e}", None


def send_telegram_message(text):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram nicht konfiguriert, überspringe Benachrichtigung.")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as e:
        print(f"Telegram-Benachrichtigung fehlgeschlagen: {e}")


def parse_date(date_str):
    if not date_str:
        return None
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def build_html(status, path="index.html"):
    items = sorted(
        status.items(),
        key=lambda kv: (
            STATUS_PRIORITY.get(kv[1]["status"], 3),
            parse_date(kv[1].get("return_date")) or datetime.max,
        ),
    )
    rows = []
    for url, info in items:
        color = {
            "verfügbar": "#1a7f37",
            "nicht verfügbar": "#cf222e",
        }.get(info["status"], "#9a6700")
        return_date = info.get("return_date") or "–"
        rows.append(
            f"""
        <tr>
          <td class="nowrap">{info['name']}</td>
          <td class="nowrap" style="color:{color}; font-weight:bold;">{info['status']}</td>
          <td class="nowrap">{return_date}</td>
        </tr>"""
        )
    html_out = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Verfügbarkeits-Check</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; background:#fafafa; }}
  .table-wrap {{ overflow-x: auto; max-width: 100%; }}
  table {{ border-collapse: collapse; width: max-content; }}
  th, td {{ border: 1px solid #ddd; padding: 0.6rem; text-align: left; }}
  td.nowrap {{ white-space: nowrap; }}
  th {{ background:#f0f0f0; }}
  h1 {{ font-size: 1.4rem; }}
  .meta {{ color:#666; font-size:0.9rem; margin-bottom:1rem;}}
</style>
</head>
<body>
<h1>Verfügbarkeits-Check</h1>
<div class="meta">Letztes Update: {datetime.now(BERLIN).strftime('%d.%m.%Y %H:%M')} Uhr</div>
<div class="table-wrap">
<table>
<tr><th>Titel</th><th>Status</th><th>Voraussichtliche Rückgabe</th></tr>
{''.join(rows)}
</table>
</div>
</body>
</html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_out)


def main():
    now = datetime.now(BERLIN)
    force = os.environ.get("FORCE_CHECK", "false").lower() == "true"
    if not force and now.hour not in TARGET_HOURS:
        print(
            f"Aktuelle Berliner Zeit {now.strftime('%H:%M')} liegt außerhalb der "
            f"Prüf-Fenster {TARGET_HOURS}. Abbruch ohne Prüfung."
        )
        return

    urls = load_urls()
    status = load_status()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for entry in urls:
            url = entry["url"]
            name = entry.get("name", url)
            old_status = status.get(url, {}).get("status")
            res_status, return_date = check_url(url, browser)

            if entry.get("notify", False) and old_status != "verfügbar" and res_status == "verfügbar":
                send_telegram_message(f"📚 Jetzt verfügbar: {name}")

            history = status.get(url, {}).get("history", [])
            history.append({"time": now.isoformat(), "status": res_status})
            history = history[-20:]
            status[url] = {
                "name": name,
                "status": res_status,
                "return_date": return_date,
                "last_checked": now.strftime("%d.%m.%Y %H:%M"),
                "history": history,
            }
        browser.close()

    save_status(status)
    build_html(status)


if __name__ == "__main__":
    main()
