"""Bridge: TrendRadar generic_webhook → collect → reformat → Lark API push.

Two modes:
  --collect : HTTP server that saves TrendRadar batches to a temp file, returns 200 immediately
  --send    : Read temp file, reformat content, send to Feishu via Lark API
"""
import os, sys, json, re
import urllib.request
import tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler

BATCH_FILE = tempfile.gettempdir() + "/tr_batches.json"

def get_token():
    app_id = os.environ["LARK_APP_ID"]
    app_secret = os.environ["LARK_APP_SECRET"]
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(url, data, {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())["tenant_access_token"]

def preserve_links(text):
    """Convert markdown links to readable format: [text](url) → text (url)"""
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1\n  \2', text)
    # Remove bold markers but keep content
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'<[^>]+>', '', text)
    return text

class CollectHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        try:
            batches = []
            if os.path.exists(BATCH_FILE):
                batches = json.loads(open(BATCH_FILE).read())
        except:
            batches = []
        batches.append(body)
        with open(BATCH_FILE, 'w') as f:
            json.dump(batches, f, ensure_ascii=False)
        print(f"[collect] batch {len(batches)}: {body.get('title','')[:50]}")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")
    def log_message(self, fmt, *args):
        pass

def run_collect(port=18900):
    HTTPServer(("127.0.0.1", port), CollectHandler).serve_forever()

def run_send():
    if not os.path.exists(BATCH_FILE):
        print("No batches to send")
        return

    chat_id = os.environ["LARK_CHAT_ID"]
    batches = json.loads(open(BATCH_FILE).read())
    token = get_token()

    for i, batch in enumerate(batches):
        title = batch.get("title", "")
        content = batch.get("content", "")
        text = preserve_links(content) if content else preserve_links(title)

        # Truncate per-batch if needed
        if len(text) > 25000:
            text = text[:25000] + "\n...(截断)"

        url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
        body = json.dumps({
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        }).encode()
        req = urllib.request.Request(url, body, {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        })
        resp = json.loads(urllib.request.urlopen(req).read())
        if resp.get("code") != 0:
            print(f"[send] batch {i+1} FAILED: {resp}", file=sys.stderr)
        else:
            print(f"[send] batch {i+1}/{len(batches)} OK: {resp['data']['message_id']}")

    # Clean up
    os.unlink(BATCH_FILE)

if __name__ == "__main__":
    if "--collect" in sys.argv:
        port = int(sys.argv[sys.argv.index("--collect")+1]) if "--collect" in sys.argv and len(sys.argv) > sys.argv.index("--collect")+1 else 18900
        run_collect(port)
    elif "--send" in sys.argv:
        run_send()
    else:
        print("Usage: notify_lark.py --collect [port] | --send", file=sys.stderr)
        sys.exit(1)
