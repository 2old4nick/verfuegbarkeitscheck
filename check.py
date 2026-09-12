import json
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

BERLIN = ZoneInfo("Europe/Berlin")
TARGET_HOURS = {10, 17}  # Uhrzeiten (Berliner Zeit), zu denen wirklich geprüft wird


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


def check_url(url):
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        r.encoding = r.apparent_encoding
        text = r.text.lower()
        if "nicht verfügbar" in text:
            return "nicht verfügbar"
        elif "verfügbar" in text:
            return "verfügbar"
        else:
            return "unbekannt"
    except Exception as e:
        return f"fehler: {e}"


def build_html(status, path="index.html"):
    rows = []
    for url, info in status.items():
        color = {
            "verfügbar": "#1a7f37",
            "nicht verfügbar": "#cf222e",
        }.get(info["status"], "#9a6700")
        rows.append(
            f"""
        <tr>
          <td><a href="{url}" target="_blank">{info['name']}</a></td>
          <td style="color:{color}; font-weight:bold;">{info['status']}</td>
          <td>{info['last_checked']}</td>
        </tr>"""
        )
    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Verfügbarkeits-Check</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; background:#fafafa; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 800px; }}
  th, td {{ border: 1px solid #ddd; padding: 0.6rem; text-align: left; }}
  th {{ background:#f0f0f0; }}
  h1 {{ font-size: 1.4rem; }}
  .meta {{ color:#666; font-size:0.9rem; margin-bottom:1rem;}}
</style>
</head>
<body>
<h1>Verfügbarkeits-Check</h1>
<div class="meta">Letztes Update: {datetime.now(BERLIN).strftime('%d.%m.%Y %H:%M')} Uhr</div>
<table>
<tr><th>Titel</th><th>Status</th><th>Zuletzt geprüft</th></tr>
{''.join(rows)}
</table>
</body>
</html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    now = datetime.now(BERLIN)
    if now.hour not in TARGET_HOURS:
        print(
            f"Aktuelle Berliner Zeit {now.strftime('%H:%M')} liegt außerhalb der "
            f"Prüf-Fenster {TARGET_HOURS}. Abbruch ohne Prüfung."
        )
        return

    urls = load_urls()
    status = load_status()

    for entry in urls:
        url = entry["url"]
        name = entry.get("name", url)
        result = check_url(url)
        history = status.get(url, {}).get("history", [])
        history.append({"time": now.isoformat(), "status": result})
        history = history[-20:]
        status[url] = {
            "name": name,
            "status": result,
            "last_checked": now.strftime("%d.%m.%Y %H:%M"),
            "history": history,
        }

    save_status(status)
    build_html(status)


if __name__ == "__main__":
    main()
