import asyncio
import aiohttp
import base64
import yaml
import re
from urllib.parse import unquote

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

async def f_s(ses, u):
    try:
        async with ses.get(u, timeout=30) as r:
            if r.status != 200: return []
            t = await r.text()
            ns = []
            try:
                d = yaml.safe_load(t)
                if isinstance(d, dict) and 'proxies' in d:
                    for p in d['proxies']:
                        if p['type'] == 'vless':
                            l = g_vl(p)
                            if l: ns.append(l)
                        elif p['type'] == 'hysteria2':
                            l = g_hy2(p)
                            if l: ns.append(l)
            except:
                pass
            if not ns:
                try: 
                    dc = base64.b64decode(t).decode('utf-8', errors='ignore')
                    t = dc
                except: pass
                vr = re.findall(r'vless://[^#]+security=reality[^#]+', t)
                h2 = re.findall(r'(?:hysteria2|hy2)://[^\s\n]+', t)
                ns.extend(vr)
                ns.extend(h2)
            return ns
    except:
        return []

async def main():
    async with aiohttp.ClientSession() as s:
        ts = [f_s(s, u) for u in SRC]
        rs = await asyncio.gather(*ts)
    an = []
    for r in rs:
        an.extend(r)
    un = list(set(an))
    if un:
        fs = "\n".join(un)
        bo = base64.b64encode(fs.encode('utf-8')).decode('utf-8')
        with open(OF, "w", encoding="utf-8") as f:
            f.write(bo)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except:
        pass