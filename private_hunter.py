import asyncio
import httpx
import base64
import re
import json
import time
from urllib.parse import unquote

# --- 核心配置：换用 2026 最稳聚合源 ---
RAW_SOURCES = [
    "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/main/all_extracted_configs.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/v2ray/all_sub.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Sub1.txt",
    "https://raw.githubusercontent.com/zipvpn/Free-V2Ray-Xray-Nodes/main/free_v2ray_xray_nodes.txt",
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub"
]

# --- 加密与筛选配置 ---
ENCRYPTION_KEY = "ODK-VPN-2026-SECRET-KEY"
ENABLE_ENCRYPTION = True

PREMIUM_REGIONS = {
    'HK': ['hk', 'hongkong', '香港', '港'],
    'JP': ['jp', 'japan', '日本', '日', '东京', '大阪'],
    'SG': ['sg', 'singapore', '新加坡', '新'],
    'TW': ['tw', 'taiwan', '台湾', '台']
}

CONCURRENT_LIMIT = 800  # 海选并发
RETEST_LIMIT = 50       # 复测并发
TIMEOUT_LIMIT = 1.0     # 握手上限
FINAL_COUNT = 50        # 保留精品数

# --- 工具函数 ---

def xor_encrypt(data: str, key: str) -> str:
    """保持你原有的 XOR 加密逻辑"""
    data_bytes, key_bytes = data.encode('utf-8'), key.encode('utf-8')
    return base64.b64encode(bytearray(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data_bytes))).decode()

def get_target(link):
    """从各协议链接中提取 Host 和 Port"""
    try:
        if link.startswith('vmess://'):
            config = json.loads(base64.b64decode(link[8:]).decode('utf-8'))
            return config.get('add'), config.get('port')
        match = re.search(r'@?([^:/?#]+):(\d+)', link)
        if match: return match.group(1), match.group(2)
    except: pass
    return None, None

async def tcp_probe(host, port, timeout=TIMEOUT_LIMIT):
    """TCP 快速探测"""
    try:
        start = time.perf_counter()
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, int(port)), timeout=timeout)
        latency = (time.perf_counter() - start) * 1000
        writer.close()
        await writer.wait_closed()
        return latency
    except:
        return None

async def stability_test(semaphore, link):
    """三轮复查选出真正稳定的精品"""
    host, port = get_target(link)
    if not host: return None
    async with semaphore:
        latencies = []
        for _ in range(3):
            lat = await tcp_probe(host, port)
            if lat: latencies.append(lat)
            await asyncio.sleep(0.05)
        if len(latencies) < 3: return None
        avg_lat = sum(latencies) / 3
        jitter = max(latencies) - min(latencies)
        score = avg_lat + (jitter * 3) # 评分模型
        return {"link": link, "avg": avg_lat, "jitter": jitter, "score": score}

# --- 主程序 ---

async def main():
    start_total = time.time()
    async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
        print("🛠️ 正在执行 30,000 级精品抓取逻辑...")
        raw_pool = set()
        
        # 1. 快速抓取全量源
        tasks = [client.get(url) for url in RAW_SOURCES]
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        for res in responses:
            if isinstance(res, httpx.Response) and res.status_code == 200:
                found = re.findall(r'(?:vmess|vless|trojan|ss|ssr|hy2)://[^\s|#|"\']+', res.text)
                raw_pool.update(found)
        
        print(f"📦 初始总数: {len(raw_pool)}")

        # 2. 地理前置过滤（HK/JP/SG/TW）
        premium_candidates = []
        for link in raw_pool:
            ps = unquote(link.split('#')[-1]).lower() if '#' in link else ""
            if any(kw in ps for kws in PREMIUM_REGIONS.values() for kw in kws):
                premium_candidates.append(link)
        
        # 3. 第一轮海选
        print(f"🚀 开启 {CONCURRENT_LIMIT} 并发海选顶级节点...")
        sem_fast = asyncio.Semaphore(CONCURRENT_LIMIT)
        async def fast_filter(l):
            h, p = get_target(l)
            if not h: return None
            async with sem_fast:
                lat = await tcp_probe(h, p)
                return {"link": l, "lat": lat} if lat else None

        initial_round = await asyncio.gather(*[fast_filter(l) for l in premium_candidates])
        candidates = sorted([r for r in initial_round if r], key=lambda x: x['lat'])[:150]
        
        # 4. 第二轮精品复测
        print(f"🏁 正在复核前 {len(candidates)} 名稳定性...")
        sem_retest = asyncio.Semaphore(RETEST_LIMIT)
        final_results = await asyncio.gather(*[stability_test(sem_retest, c['link']) for c in candidates])
        top_tier = sorted([r for r in final_results if r], key=lambda x: x['score'])[:FINAL_COUNT]

        # 5. 构建节点数据
        final_nodes = []
        for item in top_tier:
            link = item['link']
            ps = unquote(link.split('#')[-1]) if '#' in link else "Premium-Node"
            region = next((code for code, kws in PREMIUM_REGIONS.items() if any(k in ps.lower() for k in kws)), "UN")
            
            final_nodes.append({
                'id': f'node_{hash(link)%1000000}',
                'name': f"💎 {ps}",
                'countryCode': region,
                'latency': f"{int(item['avg'])}ms",
                'jitter': f"{int(item['jitter'])}ms",
                'protocol': link.split('://')[0],
                'configUrl': link,
                'config': {'add': 'auto', 'port': '443'}
            })

        # --- 导出结果（含 XOR 加密） ---
        nodes_json_str = json.dumps(final_nodes, ensure_ascii=False)
        output = {
            "data": xor_encrypt(nodes_json_str, ENCRYPTION_KEY) if ENABLE_ENCRYPTION else base64.b64encode(nodes_json_str.encode()).decode(),
            "count": len(final_nodes),
            "timestamp": str(time.time()),
            "encrypted": ENABLE_ENCRYPTION,
            "version": "2026.Premium.V1"
        }
        
        with open('nodes.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    asyncio.run(main())