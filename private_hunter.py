import asyncio
import httpx
import base64
import re
import json
import time
from urllib.parse import unquote, urlparse

S_LIST = [
    "https://raw.githubusercontent.com/barry-far/V2ray-Config/main/Sub1.txt",
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/Sub1.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/v2ray/all_sub.txt",
    "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/main/all_extracted_configs.txt",
    "https://raw.githubusercontent.com/zipvpn/Free-V2Ray-Xray-Nodes/main/free_v2ray_xray_nodes.txt",
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub"
]
# 统一输出文件名
OUT_FILE = "assets_manifest.bin"
MAX_L = 800
T_COUNT = 50
Z_D = {'1': ['hk', 'hongkong', '香港', '港'], '2': ['tw', 'taiwan', '台湾', '台'], '3': ['jp', 'japan', '日本', '日'], '4': ['sg', 'singapore', '新加坡', '新']}

async def _v(sem, link):
    try:
        protocol = link.split('://')[0]
        h, p = "", 80
        if protocol == 'vmess':
            c = json.loads(base64.b64decode(link.split('://')[1]).decode('utf-8', 'ignore'))
            h, p = c.get('add'), c.get('port')
        else:
            u = urlparse(link if '://' in link else f"http://{link}")
            h, p = u.hostname, u.port or (443 if protocol in ['vless', 'trojan', 'hy2'] else 80)
        
        if not h: return None
        
        async with sem:
            latencies = []
            for _ in range(2):
                t1 = time.perf_counter()
                f = asyncio.open_connection(h, int(p))
                _, w = await asyncio.wait_for(f, timeout=1.0)
                latencies.append((time.perf_counter() - t1) * 1000)
                w.close()
                await w.wait_closed()
            
            avg = sum(latencies) / 2
            jit = abs(latencies[0] - latencies[1])
            return {"l": link, "s": avg + (jit * 2)}
    except:
        return None

async def _run():
    async with httpx.AsyncClient(follow_redirects=True, verify=False) as c:
        tasks = [c.get(u, timeout=15.0) for u in S_LIST]
        resps = await asyncio.gather(*tasks, return_exceptions=True)
        
        raw = []
        for r in resps:
            if hasattr(r, 'text') and r.status_code == 200:
                txt = r.text
                if "://" not in txt[:50]:
                    try: txt = base64.b64decode(txt.strip()).decode('utf-8', 'ignore')
                    except: pass
                raw.extend(re.findall(r'(?:vmess|vless|trojan|ss|ssr|hy2|hysteria2)://[^\s|#|"\']+', txt))

        pool = list(set(raw))
        candidates = [l for l in pool if any(kw in unquote(l).lower() for kws in Z_D.values() for kw in kws)]
        
        sem = asyncio.Semaphore(MAX_L)
        v_tasks = [_v(sem, l) for l in candidates]
        results = await asyncio.gather(*v_tasks)
        
        valid = sorted([r for r in results if r], key=lambda x: x['s'])[:T_COUNT]
        if not valid: return
        
        out = base64.b64encode("\n".join([r['l'] for r in valid]).encode()).decode()
        with open(OUT_FILE, "w") as f:
            f.write(out)

if __name__ == "__main__":
    try:
        asyncio.run(_run())
    except:
        pass