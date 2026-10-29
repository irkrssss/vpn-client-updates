"""Official BlancVPN store sources. Fail explicitly if a store format changes."""
import re
import html
from datetime import datetime

APPLE = {"key":"blanc_apple","client":"BlancVPN","platform":"iPhone, iPad, macOS (Apple Silicon)","id":"6744585772","country":"us","url":"https://apps.apple.com/us/app/blancvpn/id6744585772"}

def required(pattern, text):
    match = re.search(pattern, text, re.S)
    if not match:
        raise ValueError("BlancVPN store metadata missing; refusing to guess a version")
    return html.unescape(match.group(1))

def fetch_rows(curl_text, fetch_json, to_local_date):
    rows = []
    url = "https://play.google.com/store/apps/details?id=com.blancvpn.app&hl=en&gl=US"
    page = curl_text(url)
    version = required(r'\[\[\["(\d+\.\d+\.\d+)"\]\],\[\[\[', page)
    date = required(r'Updated on</div><div[^>]*>([^<]+)', page)
    rows.append(dict(key="blanc_android",client="BlancVPN",platform="Android",version=version,date=datetime.strptime(date,"%b %d, %Y").strftime("%d.%m.%Y"),url=url,notes_source=""))
    url = "https://chromewebstore.google.com/detail/fbnnaeejnbpbbkmnieomfamekibceoob?hl=en"
    page = curl_text(url)
    version = required(r'>Version</div><div[^>]*>([0-9.]+)</div>',page)
    date = required(r'>Updated</div><div[^>]*>([^<]+)</div>',page)
    rows.append(dict(key="blanc_chrome",client="BlancVPN",platform="Chrome / Chromium (расширение)",version=version,date=datetime.strptime(date,"%B %d, %Y").strftime("%d.%m.%Y"),url=url,notes_source=""))
    data=fetch_json("https://addons.mozilla.org/api/v5/addons/addon/blancvpn-fast-and-secure-proxy/")
    current=data["current_version"]
    rows.append(dict(key="blanc_firefox",client="BlancVPN",platform="Firefox (расширение)",version=current["version"],date=to_local_date(current["file"]["created"]),url="https://addons.mozilla.org/en-US/firefox/addon/blancvpn-fast-and-secure-proxy/",notes_source=""))
    return rows
