import asyncio
import aiohttp
import base64
import json
import re
import time
from urllib.parse import unquote

TR = ['hk', 'hongkong', 'tw', 'taiwan', 'jp', 'japan', 'sg', 'singapore', 'us', 'usa', 'united states']
SRC = [
    "https://raw.githubusercontent.com/barry-far/V2ray-Config/main/Sub1.txt",
    "https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/v2ray.txt",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/EternityAir",
    "https://raw.githubusercontent.com/yebekhe/TelegramV2rayCollector/main/sub/normal/mix",
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub"
]
OF = "assets_manifest.bin"
TO = 3.0

def p_n(l):
    try:
        s, r = l.split('://', 1)
        h, pt, ps = None, None, ''
        if s == 'vmess':
            mp = len(r) % 4
            if mp: r += '=' * (4 - mp)
            d = json.loads(base64.b64decode(r).decode('utf-8'))
            h = d.get('add')
            pt = d.get('port')
            ps = d.get('ps', '')
        else:
            if '#' in r:
                r, ps = r.split('#', 1)
                ps = unquote(ps)
            if '@' in r:
                _, sp = r.split('@', 1)
            else:
                sp = r
            if ':' in sp:
                m = re.search(r'\[?([^\]]+)\]?:(\d+)', sp)
                if m:
                    h = m.group(1)
                    pt = m.group(2)
                if h and '?' in h:
                    h = h.split('?')[0]
        return {'l': l, 'h': h, 'pt': int(pt) if pt else 443, 'ps': ps}
    except:
        return None

async def c_n(sem, n):
    if not n or not n['h']: return None
    pl = n['ps'].lower() if n['ps'] else ''
    if not any(k in pl for k in TR):
        return None
    async with sem:
        try:
            st = time.time()
            c = asyncio.open_connection(n['h'], n['pt'])
            _, w = await asyncio.wait_for(c, timeout=TO)
            lat = (time.time() - st) * 1000
            w.close()
            await w.wait_closed()
            return {'l': n['l'], 'lat': lat}
        except:
            return None

async def m():
    al = []
    async with aiohttp.ClientSession() as s:
        for u in SRC:
            try:
                async with s.get(u, timeout=15) as r:
                    t = await r.text()
                    try: c = base64.b64decode(t).decode('utf-8', errors='ignore')
                    except: c = t
                    lks = re.findall(r'(?:vmess|vless|trojan|ss|ssr|hy2)://[^\s\n]+', c)
                    al.extend(lks)
            except: pass
    ul = list(set(al))
    pn = []
    for l in ul:
        i = p_n(l)
        if i: pn.append(i)
    sem = asyncio.Semaphore(200)
    tsk = [c_n(sem, n) for n in pn]
    res = await asyncio.gather(*tsk)
    vn = [r for r in res if r is not None]
    vn.sort(key=lambda x: x['lat'])
    tp = vn[:50]
    if tp:
        fc = "\n".join([n['l'] for n in tp])
        bd = base64.b64encode(fc.encode('utf-8')).decode('utf-8')
        with open(OF, "w", encoding="utf-8") as f:
            f.write(bd)

if __name__ == "__main__":
    asyncio.run(m())