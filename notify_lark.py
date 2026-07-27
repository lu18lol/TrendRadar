"""Read TrendRadar HTML report and push to Feishu via Lark API."""
import os, sys, json, re
import urllib.request
from html.parser import HTMLParser

APP_ID = os.environ["LARK_APP_ID"]
APP_SECRET = os.environ["LARK_APP_SECRET"]
CHAT_ID = os.environ["LARK_CHAT_ID"]

def get_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode()
    req = urllib.request.Request(url, data, {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["tenant_access_token"]

def send_lark(text):
    token = get_token()
    # Split long messages into chunks (Feishu text limit ~30KB)
    chunks = []
    current = ""
    for line in text.split('\n'):
        if len(current) + len(line) + 1 > 25000:
            chunks.append(current)
            current = line
        else:
            current = current + '\n' + line if current else line
    if current:
        chunks.append(current)

    for i, chunk in enumerate(chunks):
        url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
        body = json.dumps({
            "receive_id": CHAT_ID,
            "msg_type": "text",
            "content": json.dumps({"text": chunk}),
        }).encode()
        req = urllib.request.Request(url, body, {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        })
        resp = json.loads(urllib.request.urlopen(req).read())
        if resp.get("code") != 0:
            print(f"Lark API error: {resp}", file=sys.stderr)
        else:
            print(f"  Chunk {i+1}/{len(chunks)} sent: {resp['data']['message_id']}")

def extract_report(html_path):
    """Extract plain text content from TrendRadar HTML report"""
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.lines = []
            self.skip = False
            self.in_style = False
            self.in_script = False
            self.in_head = False
            self.current = ""

        def handle_starttag(self, tag, attrs):
            if tag in ('style', 'script'):
                self.in_style = True
            if tag in ('br', 'hr', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'div', 'p'):
                if self.current.strip():
                    self.lines.append(self.current.strip())
                    self.current = ""

        def handle_endtag(self, tag):
            if tag in ('style', 'script'):
                self.in_style = False
            if tag in ('br', 'p', 'div', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'hr'):
                if self.current.strip():
                    self.lines.append(self.current.strip())
                    self.current = ""

        def handle_data(self, data):
            if self.in_style or self.in_script:
                return
            text = data.strip()
            if text:
                self.current += " " + text if self.current else text

    extractor = TextExtractor()
    extractor.feed(html)
    if extractor.current.strip():
        extractor.lines.append(extractor.current.strip())

    # Deduplicate and filter empty/irrelevant lines
    seen = set()
    clean = []
    for line in extractor.lines:
        if line and line not in seen and len(line) > 2:
            # Skip css/js noise
            if line.startswith('.') or line.startswith('{') or line.startswith('}'):
                continue
            if line.startswith('function') or line.startswith('var ') or line.startswith('const '):
                continue
            seen.add(line)
            clean.append(line)

    return '\n'.join(clean[:200])  # cap at 200 lines


def main():
    html_path = "output/html/latest/current.html"
    if not os.path.exists(html_path):
        print(f"No HTML report at {html_path}", file=sys.stderr)
        sys.exit(0)

    text = extract_report(html_path)
    if len(text) < 50:
        print(f"Report too short ({len(text)} chars), may be empty", file=sys.stderr)
        sys.exit(0)

    print(f"Extracted {len(text)} chars from report")
    send_lark(text)


if __name__ == "__main__":
    main()
