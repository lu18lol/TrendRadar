"""Bridge: receive TrendRadar generic_webhook, forward to Feishu via Lark API.

Two modes:
  --server : run as HTTP server, TrendRadar POSTs to it, forward each batch to Lark
  default  : stdin mode, send raw text to Lark (fallback)
"""
import os, sys, json, re
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

APP_ID = os.environ["LARK_APP_ID"]
APP_SECRET = os.environ["LARK_APP_SECRET"]
CHAT_ID = os.environ["LARK_CHAT_ID"]

_token = None

def get_token():
    global _token
    if _token:
        return _token
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode()
    req = urllib.request.Request(url, data, {"Content-Type": "application/json"})
    _token = json.loads(urllib.request.urlopen(req).read())["tenant_access_token"]
    return _token

def send_lark(text):
    token = get_token()
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
        return False
    print(f"  -> Lark sent: {resp['data']['message_id']}")
    return True

def strip_markdown(text):
    """Remove markdown formatting characters for plain text display."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'<[^>]+>', '', text)
    return text

class BridgeHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        title = body.get("title", "")
        content = body.get("content", "")

        # TrendRadar sends markdown content; strip tags for plain text Lark
        clean_title = strip_markdown(title)
        clean_content = strip_markdown(content)
        msg = clean_content if clean_content else f"{clean_title}\n\n{clean_content}"
        if not msg.strip():
            msg = clean_title

        # Truncate if needed
        if len(msg) > 28000:
            msg = msg[:28000] + "\n...[截断]"

        print(f"Batch: {len(msg)} chars | {clean_title[:50] if clean_title else '-'}")
        ok = send_lark(msg)
        self.send_response(200 if ok else 500)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, format, *args):
        print(f"[bridge] {args[0]}")


def run_server(port=18900):
    server = HTTPServer(("127.0.0.1", port), BridgeHandler)
    print(f"Bridge listening on 127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    if "--server" in sys.argv:
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 18900
        run_server(port)
    else:
        # Fallback: read from stdin
        text = sys.stdin.read().strip()
        if text:
            send_lark(text)
        else:
            print("No input", file=sys.stderr)
