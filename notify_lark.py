"""Extract TrendRadar news from SQLite + console output, send to Feishu via Lark API."""
import os, sys, json, re, sqlite3, glob
import urllib.request
from datetime import datetime

APP_ID = os.environ["LARK_APP_ID"]
APP_SECRET = os.environ["LARK_APP_SECRET"]
CHAT_ID = os.environ["LARK_CHAT_ID"]

def get_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode()
    req = urllib.request.Request(url, data, {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["tenant_access_token"]

def send_msg(token, text):
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
    body = json.dumps({
        "receive_id": CHAT_ID,
        "msg_type": "text",
        "content": json.dumps({"text": text}),
    }).encode()
    req = urllib.request.Request(url, body, {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    })
    resp = json.loads(urllib.request.urlopen(req).read())
    if resp.get("code") != 0:
        print(f"Lark API error: {resp}", file=sys.stderr)
        sys.exit(1)
    print(f"Message sent: {resp['data']['message_id']}")

def load_keywords():
    """Load frequency words from config"""
    words = []
    try:
        with open("config/frequency_words.txt") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    words.append(line)
    except FileNotFoundError:
        pass
    return words

def get_latest_news():
    """Get latest news from SQLite, filtered by keywords"""
    db_files = sorted(glob.glob("output/news/*.db"), reverse=True)
    if not db_files:
        return None

    keywords = load_keywords()

    conn = sqlite3.connect(db_files[0])
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get the latest crawl time
    cur.execute("SELECT MAX(last_crawl_time) as t FROM news_items")
    row = cur.fetchone()
    if not row or not row["t"]:
        conn.close()
        return None
    latest = row["t"]

    # Get news from the latest crawl, join with platform name, filter by keywords
    cur.execute("""
        SELECT n.title, p.name as platform, n.rank, n.url
        FROM news_items n
        JOIN platforms p ON n.platform_id = p.id
        WHERE n.last_crawl_time = ?
        ORDER BY n.rank ASC
    """, (latest,))

    all_news = cur.fetchall()
    conn.close()

    if not all_news:
        return None

    # Filter by keyword
    if keywords:
        matched = []
        for item in all_news:
            title = item["title"].lower()
            for kw in keywords:
                if kw.lower() in title:
                    matched.append(dict(item))
                    break
    else:
        matched = [dict(item) for item in all_news]

    return {
        "total": len(all_news),
        "matched": matched[:30],  # cap at 30 headlines
        "platforms": list(set(item["platform"] for item in all_news)),
    }

def format_news(news_items):
    """Format news items into text lines"""
    lines = []
    seen = set()
    for item in news_items:
        title = item["title"]
        platform = item["platform"]
        # Deduplicate by title
        if title in seen:
            continue
        seen.add(title)
        # Truncate long titles
        if len(title) > 50:
            title = title[:48] + ".."
        lines.append(f"· [{platform}] {title}")
    return lines

def main():
    news = get_latest_news()

    # Also parse console output for stats
    console = sys.stdin.read()
    info = {}
    for line in console.split('\n'):
        m = re.search(r'当前榜单.*?(\d+) 条.*?频率词匹配', line)
        if m: info['hotlist_match'] = m.group(1)
        m = re.search(r'新增热点过滤后：(\d+) 条', line)
        if m: info['new_count'] = m.group(1)

    now = datetime.now().strftime('%m-%d %H:%M')

    parts = [f"🔥 TrendRadar 热点推送 | {now}\n"]

    if news:
        stats = f"共抓取 {news['total']} 条，命中 {len(news['matched'])} 条，覆盖 {len(news['platforms'])} 个平台\n"
        parts.append(stats)

        headlines = format_news(news['matched'])
        if headlines:
            parts.append("—" * 20)
            parts.extend(headlines)
    elif info:
        parts.append(f"热榜命中：{info.get('hotlist_match', '?')} 条")

    repo = os.environ.get('GITHUB_REPOSITORY', 'lu18lol/TrendRadar')
    parts.append(f"\n完整报告：https://github.com/{repo}")

    msg = '\n'.join(parts)
    # Feishu text limit is ~30KB, truncate if needed
    if len(msg) > 28000:
        msg = msg[:28000] + "\n...（内容过长已截断）"

    print(f"Sending {len(msg)} chars...")
    token = get_token()
    send_msg(token, msg)

if __name__ == "__main__":
    main()
