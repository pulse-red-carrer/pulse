"""
Pulse by Red Career — Automated Finance News Fetcher
Uses RSS feeds (100% free, no API key, commercial use OK)
Simplifies news with Grok AI, saves to news_data.json
"""
import json, requests, re
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
import os

GROK_API_KEY   = os.environ["GROK_API_KEY"]
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── 100% FREE RSS FEEDS ────────────────────────────────────────────────────
RSS_FEEDS = [
    # India
    {"url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",  "label": "India",  "source": "Economic Times"},
    {"url": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms","label": "India", "source": "ET Markets"},
    {"url": "https://www.moneycontrol.com/rss/MCtopnews.xml",                         "label": "India",  "source": "Moneycontrol"},
    {"url": "https://www.livemint.com/rss/markets",                                   "label": "India",  "source": "LiveMint"},
    {"url": "https://www.business-standard.com/rss/markets-106.rss",                  "label": "India",  "source": "Business Standard"},
    # USA / Global
    {"url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US", "label": "USA", "source": "Yahoo Finance"},
    {"url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^DJI&region=US&lang=en-US",  "label": "USA", "source": "Yahoo Finance"},
    {"url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",                  "label": "USA",    "source": "CNBC"},
    {"url": "https://www.cnbc.com/id/10000664/device/rss/rss.html",                   "label": "Global", "source": "CNBC World"},
    {"url": "https://feeds.reuters.com/reuters/businessNews",                          "label": "Global", "source": "Reuters"},
    # Commodities
    {"url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=GC=F&region=US&lang=en-US",  "label": "Commodities", "source": "Yahoo Finance"},
    {"url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=CL=F&region=US&lang=en-US",  "label": "Commodities", "source": "Yahoo Finance"},
    # Crypto
    {"url": "https://feeds.finance.yahoo.com/rss/2.0/headline?s=BTC-USD&region=US&lang=en-US","label": "Crypto", "source": "Yahoo Finance"},
    {"url": "https://cointelegraph.com/rss",                                           "label": "Crypto", "source": "CoinTelegraph"},
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PulseBot/1.0)"}

def clean(text):
    if not text: return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&#\d+;', '', text)
    return text.strip()

def parse_rss(feed):
    articles = []
    try:
        r = requests.get(feed["url"], headers=HEADERS, timeout=15)
        root = ET.fromstring(r.content)
        ns = {'media': 'http://search.yahoo.com/mrss/'}
        items = root.findall('.//item')
        for item in items[:6]:
            title = clean(item.findtext('title', ''))
            desc  = clean(item.findtext('description', ''))
            url   = item.findtext('link', '') or item.findtext('{http://www.w3.org/2005/Atom}link', '')
            pub   = item.findtext('pubDate', item.findtext('published', ''))
            # Try to get image from media:thumbnail or enclosure
            img = ''
            media = item.find('media:thumbnail', ns) or item.find('media:content', ns)
            if media is not None:
                img = media.get('url', '')
            if not img:
                enc = item.find('enclosure')
                if enc is not None and 'image' in enc.get('type', ''):
                    img = enc.get('url', '')
            if not img:
                # Try to extract image from description HTML
                m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', item.findtext('description', ''))
                if m: img = m.group(1)

            # Parse date
            try:
                from email.utils import parsedate_to_datetime
                pub_iso = parsedate_to_datetime(pub).astimezone(timezone.utc).isoformat()
            except:
                pub_iso = datetime.now(timezone.utc).isoformat()

            if title and len(title) > 10 and '[Removed]' not in title:
                articles.append({
                    "title": title,
                    "description": desc[:300] if desc else "",
                    "url": url,
                    "image": img,
                    "source": feed["source"],
                    "published_at": pub_iso,
                    "category": feed["label"],
                    "simple_explanation": ""
                })
    except Exception as e:
        print(f"  RSS error {feed['source']}: {e}")
    return articles

def simplify(title, desc):
    try:
        r = requests.post("https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROK_API_KEY}", "Content-Type": "application/json"},
            json={"model": "grok-3-latest", "max_tokens": 200, "messages": [{"role": "user", "content":
                f"""You are a friendly finance teacher explaining news to a 12-year-old student.

Your job:
1. Explain WHAT happened in very simple words
2. Explain WHY it happened (the reason behind it)
3. Explain HOW it affects common people like you and me

Rules:
- Use everyday simple words — NO finance jargon at all
- Write like you are talking to a curious 12-year-old
- Use simple examples or comparisons if needed (like "think of it like your pocket money...")
- Write 4-5 sentences total
- Be friendly, clear and interesting

News Title: {title}
News Description: {desc or ''}

Write ONLY the simple explanation. No intro, no labels, just the explanation."""}]},
            timeout=20)
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  Grok error: {e}")
        return desc[:200] if desc else ""

def send_telegram(articles):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT: return
    emojis = {"India":"🇮🇳","USA":"🇺🇸","Global":"🌍","Commodities":"🥇","Crypto":"₿"}
    now = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    msg = f"📊 *Pulse by Red Career* — {now}\n\n"
    for a in articles[:5]:
        e = emojis.get(a["category"], "📰")
        msg += f"{e} *{a['title'][:80]}*\n_{a['simple_explanation'][:130]}_\n[Read more]({a['url']})\n\n"
    msg += f"_🔴 {len(articles)} stories updated · Pulse by Red Career_"
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True},
            timeout=10)
        print("✅ Telegram alert sent!")
    except Exception as e:
        print(f"  Telegram error: {e}")

def main():
    print(f"\n🔴 Pulse by Red Career — started {datetime.now(timezone.utc).isoformat()}")
    print("📡 Fetching from RSS feeds...")
    articles, seen = [], set()
    for feed in RSS_FEEDS:
        print(f"   → {feed['source']} ({feed['label']})")
        for a in parse_rss(feed):
            if a["url"] not in seen:
                seen.add(a["url"])
                articles.append(a)
    articles.sort(key=lambda x: x["published_at"], reverse=True)
    articles = articles[:40]
    print(f"   Total: {len(articles)} articles")

    print("🤖 Simplifying with Grok AI...")
    for i, a in enumerate(articles):
        print(f"   [{i+1}/{len(articles)}] {a['title'][:55]}...")
        a["simple_explanation"] = simplify(a["title"], a["description"])

    with open("news_data.json", "w", encoding="utf-8") as f:
        json.dump({"last_updated": datetime.now(timezone.utc).isoformat(),
                   "total": len(articles), "articles": articles}, f, ensure_ascii=False, indent=2)
    print(f"💾 Saved {len(articles)} articles to news_data.json")

    print("📲 Sending Telegram alert...")
    send_telegram(articles)
    print("✅ All done!\n")

if __name__ == "__main__":
    main()
