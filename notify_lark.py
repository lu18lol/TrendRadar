"""Parse TrendRadar output and send summary to Feishu group via Lark API."""
import os, sys, json, re
import urllib.request

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

def parse_output(text):
    lines = text.split('\n')
    info = {}

    # Extract key stats
    for line in lines:
        m = re.search(r'(\d+) 条当前榜单新闻中有 (\d+) 条频率词匹配', line)
        if m: info['hotlist_match'] = f"{m.group(2)}/{m.group(1)}"

        m = re.search(r'\[RSS\] 关键词分组统计：(\d+)/(\d+)', line)
        if m: info['rss_match'] = f"{m.group(1)}/{m.group(2)}"

        m = re.search(r'新增热点过滤后：(\d+) 条保留', line)
        if m: info['new_items'] = m.group(1)

        m = re.search(r'\[AI\].*分析', line)
        if m: info['ai'] = m.group(0).strip()

        m = re.search(r'成功: \[(.+?)\]', line)
        if m:
            platforms = [p.strip("'") for p in m.group(1).split(', ')]
            info['platform_count'] = len(platforms)

    return info

def main():
    text = sys.stdin.read()

    info = parse_output(text)

    parts = ["🔥 TrendRadar 热点推送\n"]

    if info.get('hotlist_match'):
        parts.append(f"热榜命中：{info['hotlist_match']} 条")

    if info.get('rss_match'):
        parts.append(f"RSS 命中：{info['rss_match']} 条")

    if info.get('new_items'):
        parts.append(f"新增热点：{info['new_items']} 条")

    if info.get('platform_count'):
        parts.append(f"监控平台：{info['platform_count']} 个")

    parts.append(f"\n完整报告：https://github.com/{os.environ.get('GITHUB_REPOSITORY', 'lu18lol/TrendRadar')}")

    msg = '\n'.join(parts)
    print(f"Sending:\n{msg}")

    token = get_token()
    send_msg(token, msg)

if __name__ == "__main__":
    main()
