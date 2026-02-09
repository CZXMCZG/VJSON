import requests
import base64
import yaml
import re
import sys
import urllib3
from urllib.parse import unquote

# 禁用SSL警告，防止日志刷屏
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# 强制UTF-8
sys.stdout.reconfigure(encoding='utf-8')

SRC = [
    "https://raw.githubusercontent.com/anaer/Sub/main/clash.yaml",
    "https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/clash.yml",
    "https://raw.githubusercontent.com/juewuy/ShellClash/master/public/public_servers.yml",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/EternityAir",
    "https://raw.githubusercontent.com/yebekhe/TelegramV2rayCollector/main/sub/normal/hysteria2",
    "https://raw.githubusercontent.com/yebekhe/TelegramV2rayCollector/main/sub/normal/vless",
]
OF = "assets_manifest.bin"

def g_vl(p):
    try:
        u = p.get('uuid')
        s = p.get('server')
        pt = p.get('port')
        n = p.get('name', 'VLESS')
        pm = f"?security={p.get('cipher', 'auto')}&type={p.get('network', 'tcp')}"
        
        if p.get('tls'):
            pm += "&security=tls"
            if p.get('servername'): pm += f"&sni={p['servername']}"
            if p.get('reality-opts'):
                r = p['reality-opts']
                pb = r.get('public-key', '')
                fp = r.get('fingerprint', 'chrome')
                sid = r.get('short-id', '')
                if pb:
                    pm += f"&security=reality&pbk={pb}&fp={fp}&sid={sid}&sni={p.get('servername','')}"
        
        if 'security=reality' in pm or 'security=tls' in pm:
            return f"vless://{u}@{s}:{pt}{pm}#{unquote(str(n))}"
        return None
    except:
        return None

def g_hy2(p):
    try:
        pw = p.get('password', '')
        s = p.get('server')
        pt = p.get('port')
        n = p.get('name', 'Hy2')
        sn = p.get('sni', '')
        ins = 1 if p.get('skip-cert-verify') else 0
        return f"hysteria2://{pw}@{s}:{pt}?insecure={ins}&sni={sn}#{unquote(str(n))}"
    except:
        return None

def fetch_source(url):
    print(f"Fetch: {url}")
    try:
        # 使用 requests，设置verify=False提高成功率
        resp = requests.get(url, timeout=30, verify=False)
        if resp.status_code != 200: return []
        text = resp.text
        ns = []
        
        try:
            d = yaml.safe_load(text)
            if isinstance(d, dict) and 'proxies' in d:
                for p in d['proxies']:
                    if p['type'] == 'vless':
                        l = g_vl(p)
                        if l: ns.append(l)
                    elif p['type'] == 'hysteria2':
                        l = g_hy2(p)
                        if l: ns.append(l)
        except: pass

        if not ns:
            try: 
                dc = base64.b64decode(text).decode('utf-8', errors='ignore')
                text = dc
            except: pass
            
            vr = re.findall(r'vless://[^#]+security=reality[^#]+', text)
            h2 = re.findall(r'(?:hysteria2|hy2)://[^\s\n]+', text)
            ns.extend(vr)
            ns.extend(h2)
        return ns
    except Exception as e:
        print(f"Err: {e}")
        return []

def main():
    print("Start Hunting...")
    all_nodes = []
    for url in SRC:
        nodes = fetch_source(url)
        all_nodes.extend(nodes)
    
    unique_nodes = list(set(all_nodes))
    print(f"Got {len(unique_nodes)} unique nodes")
    
    if unique_nodes:
        fs = "\n".join(unique_nodes)
        bo = base64.b64encode(fs.encode('utf-8')).decode('utf-8')
        with open(OF, "w", encoding="utf-8") as f:
            f.write(bo)
        print("Saved.")

if __name__ == "__main__":
    main()