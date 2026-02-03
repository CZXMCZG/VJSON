import asyncio
import httpx
import base64
import re
import json
import time
from urllib.parse import unquote

# --- 2026 顶级聚合源（实时更新） ---
RAW_SOURCES = [
    "https://raw.githubusercontent.com/barry-far/V2ray-Config/main/Sub1.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-Config/main/Sub2.txt",
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/Sub1.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/v2ray/all_sub.txt",
    "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/main/all_extracted_configs.txt",
    "https://raw.githubusercontent.com/mfuu/v2ray/main/v2ray",
    "https://raw.githubusercontent.com/Vauth/node/raw/main/Main",
    "https://raw.githubusercontent.com/zipvpn/Free-V2Ray-Xray-Nodes/main/free_v2ray_xray_nodes.txt",
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub",
    "https://raw.githubusercontent.com/tbbatbb/Proxy/master/dist/v2ray.txt"
]

# --- 筛选与加密配置 ---
ENCRYPTION_KEY = "ODK-VPN-2026-SECRET-KEY"
ENABLE_ENCRYPTION = True

# 物理延迟最低的顶级机房区域
PREMIUM_REGIONS = {
    'HK': ['hk', 'hongkong', '香港', '港'],
    'JP': ['jp', 'japan', '日本', '日', '东京', '大阪'],
    'SG': ['sg', 'singapore', '新加坡', '新'],
    'TW': ['tw', 'taiwan', '台湾', '台']
}

CONCURRENT_LIMIT = 1000  # 3万节点级别，海选并发拉满
RETEST_LIMIT = 50        # 复测需精准，保持低并发
TIMEOUT_LIMIT = 1.0      # 超过1秒的直接淘汰
FINAL_COUNT = 50        # 最终精选50个

# --- 工具函数 ---

def xor_encrypt(data: str, key: str) -> str:
    data_bytes, key_bytes = data.encode('utf-8'), key.encode('utf-8')
    return base64.b64encode(bytearray(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data_bytes))).decode()

def get_target(link):
    try:
        if link.startswith('vmess://'):
            config = json.loads(base64.b64decode(link[8:]).decode('utf-8'))
            return config.get('add'), config.get('port')
        match = re.search(r'@?([^:/?#]+):(\d+)', link)
        if match: return match.group(1), match.group(2)
    except: pass
    return None, None

async def tcp_probe(host, port, timeout=TIMEOUT_LIMIT):
    try:
        start = time.perf_counter()
        # 2026 暴力探测：只做 TCP 三次握手
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, int(port)), timeout=timeout)
        latency = (time.perf_counter() - start) * 1000
        writer.close()
        await writer.wait_closed()
        return latency
    except:
        return None

async def stability_test(semaphore, link):
    host, port = get_target(link)
    if not host: return None
    async with semaphore:
        lats = []
        for _ in range(3):
            l = await tcp_probe(host, port)
            if l: lats.append(l)
        if len(lats) < 3: return None
        avg = sum(lats) / 3
        jitter = max(lats) - min(lats)
        return {"link": link, "avg": avg, "jitter": jitter, "score": avg + jitter * 3}

# --- 主逻辑 ---

async def main():
    print(f"🚀 [2026-02] 启动顶级精品挖掘引擎...")
    start_time = time.time()
    
    async with httpx.AsyncClient(verify=False, timeout=20.0, follow_redirects=True) as client:
        # 1. 并发抓取
        print(f"📥 正在扫描 {len(RAW_SOURCES)} 个全量订阅源...")
        raw_pool = set()
        fetch_tasks = [client.get(url) for url in RAW_SOURCES]
        responses = await asyncio.gather(*fetch_tasks, return_exceptions=True)
        
        for res in responses:
            if isinstance(res, httpx.Response) and res.status_code == 200:
                # 兼容 Base64 格式
                content = res.text
                if "://" not in content[:50]:
                    try: content = base64.b64decode(content).decode('utf-8', 'ignore')
                    except: pass
                found = re.findall(r'(?:vmess|vless|trojan|ss|ssr|hy2)://[^\s|#|"\']+', content)
                raw_pool.update(found)
        
        print(f"📦 发现原始节点: {len(raw_pool)} 个")

        # 2. 地理预过滤（仅限 HK/JP/SG/TW）
        premium_links = [l for l in raw_pool if any(kw in unquote(l).lower() for kws in PREMIUM_REGIONS.values() for kw in kws)]
        print(f"🎯 区域锁定完成，候选精品: {len(premium_links)} 个")

        # 3. 第一轮：海选
        sem_fast = asyncio.Semaphore(CONCURRENT_LIMIT)
        async def fast_op(l):
            h, p = get_target(l)
            if not h: return None
            async with sem_fast:
                lat = await tcp_probe(h, p)
                return {"link": l, "lat": lat} if lat else None

        results = await asyncio.gather(*[fast_op(l) for l in premium_links])
        candidates = sorted([r for r in results if r], key=lambda x: x['lat'])[:150]
        
        # 4. 第二轮：精品复测
        print(f"💎 正在对前 {len(candidates)} 名进行稳定性复压测试...")
        sem_re = asyncio.Semaphore(RETEST_LIMIT)
        final_list = await asyncio.gather(*[stability_test(sem_re, c['link']) for c in candidates])
        top_tier = sorted([r for r in final_list if r], key=lambda x: x['score'])[:FINAL_COUNT]

        # 5. 数据封装与加密
        final_nodes = []
        for item in top_tier:
            link = item['link']
            name = unquote(link.split('#')[-1]) if '#' in link else "Premium-Node"
            final_nodes.append({
                'id': f'n_{hash(link)%1000000}',
                'name': f"⚡ {name}",
                'latency': f"{int(item['avg'])}ms",
                'jitter': f"{int(item['jitter'])}ms",
                'configUrl': link,
                'region': next((k for k, v in PREMIUM_REGIONS.items() if any(kw in name.lower() for kw in v)), "UN")
            })

        output = {
            "data": xor_encrypt(json.dumps(final_nodes, ensure_ascii=False), ENCRYPTION_KEY) if ENABLE_ENCRYPTION else final_nodes,
            "count": len(final_nodes),
            "timestamp": time.time()
        }
        
        with open('nodes.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 选拔结束！耗时: {time.time() - start_time:.2f}s")
        print(f"🏆 已存入 {len(final_nodes)} 个顶级加密精品节点到 nodes.json")

if __name__ == "__main__":
    asyncio.run(main())