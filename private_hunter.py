import asyncio
import aiohttp
import base64
import json
import re
import time
from urllib.parse import unquote, urlparse

# --- 中国特化配置 ---
# 优质线路关键词（加分项）
G_KW = ['cn2', 'gia', '9929', '4837', 'cmcc', 'cu', 'ct', 'premium', 'vip']
# 必选地区（白名单）
REGIONS = ['hk', 'hongkong', 'tw', 'taiwan', 'jp', 'japan', 'sg', 'singapore', 'kr', 'korea', 'us', 'usa']
# 协议优先级：Hy2 > Vless > Trojan > Vmess
P_SCORE = {'hysteria2': 50, 'hy2': 50, 'vless': 40, 'trojan': 30, 'vmess': 10, 'ss': 10}

SRC = [
    "https://raw.githubusercontent.com/barry-far/V2ray-Config/main/Sub1.txt",
    "https://raw.githubusercontent.com/ermaozi/get_subscribe/main/subscribe/v2ray.txt",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/EternityAir",
    "https://raw.githubusercontent.com/yebekhe/TelegramV2rayCollector/main/sub/normal/mix",
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub",
    "https://raw.githubusercontent.com/anaer/Sub/main/clash.yaml" 
]
OF = "assets_manifest.bin"
TO = 2.5 # 缩短超时，排除掉那些响应慢的假节点

def get_info(l):
    try:
        p = l.split('://')[0]
        h, pt, ps = None, None, ''
        
        if p == 'vmess':
            r = l.split('://')[1]
            mp = len(r) % 4
            if mp: r += '=' * (4 - mp)
            d = json.loads(base64.b64decode(r).decode('utf-8'))
            h, pt, ps = d.get('add'), d.get('port'), d.get('ps', '')
        else:
            u = urlparse(l if '://' in l else f"http://{l}")
            h, pt = u.hostname, u.port or 443
            ps = unquote(u.fragment) if u.fragment else ''
            
        return {'l': l, 'h': h, 'pt': int(pt), 'ps': ps, 'prot': p}
    except:
        return None

def calc_score(n):
    # 基础分：协议
    s = P_SCORE.get(n['prot'], 0)
    
    # 地区分
    n_ps = n['ps'].lower()
    if any(r in n_ps for r in ['hk', 'hongkong']): s += 30
    elif any(r in n_ps for r in ['tw', 'taiwan']): s += 25
    elif any(r in n_ps for r in ['jp', 'japan', 'sg']): s += 20
    
    # 线路分 (CN2/GIA等)
    if any(k in n_ps for k in G_KW): s += 50
    
    # 端口分 (443/80 优先)
    if n['pt'] in [443, 80, 8080, 2053, 2083]: s += 15
    
    return s

async def test_node(sem, n):
    if not n or not n['h']: return None
    
    # 只要名字里不包含目标地区，直接扔，不浪费时间测速
    if not any(r in n['ps'].lower() for r in REGIONS): return None

    async with sem:
        try:
            st = time.time()
            # 只做极速握手，模拟国内对延迟的苛刻要求
            c = asyncio.open_connection(n['h'], n['pt'])
            _, w = await asyncio.wait_for(c, timeout=TO)
            lat = (time.time() - st) * 1000
            w.close()
            await w.wait_closed()
            
            # 计算最终得分：分数高 + 延迟低
            final_score = calc_score(n) - (lat * 0.1) 
            return {'l': n['l'], 'score': final_score}
        except:
            return None

async def run():
    async with aiohttp.ClientSession() as s:
        tasks = [s.get(u, timeout=15) for u in SRC]
        res = await asyncio.gather(*tasks, return_exceptions=True)
    
    raw = []
    for r in res:
        try:
            if hasattr(r, 'status') and r.status == 200:
                t = await r.text()
                # 尝试Base64解密
                try: c = base64.b64decode(t).decode('utf-8', errors='ignore')
                except: c = t
                raw.extend(re.findall(r'(?:vmess|vless|trojan|ss|ssr|hy2|hysteria2)://[^\s\n]+', c))
        except: pass
    
    # 去重
    pool = list(set(raw))
    nodes = []
    for l in pool:
        i = get_info(l)
        if i: nodes.append(i)
        
    sem = asyncio.Semaphore(300) # 提高并发
    res = await asyncio.gather(*[test_node(sem, n) for n in nodes])
    
    # 筛选有效且分数最高的
    valid = [r for r in res if r]
    # 按分数从高到低排序
    valid.sort(key=lambda x: x['score'], reverse=True)
    
    # 取前60个，确保有足够备选
    final = valid[:60]
    
    if final:
        out = base64.b64encode("\n".join([x['l'] for x in final]).encode('utf-8')).decode('utf-8')
        with open(OF, "w") as f:
            f.write(out)

if __name__ == "__main__":
    asyncio.run(run())