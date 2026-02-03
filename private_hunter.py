import asyncio
import httpx
import base64
import re
import json
import random
import time
from urllib.parse import unquote, urlparse

# --- 核心配置 ---
RAW_SOURCES = [
    "https://raw.githubusercontent.com/barry-far/V2ray-Config/main/Sub1.txt",
    "https://raw.githubusercontent.com/Epodonios/v2ray-configs/main/Sub1.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/v2ray/all_sub.txt",
    "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/main/all_extracted_configs.txt",
    "https://raw.githubusercontent.com/zipvpn/Free-V2Ray-Xray-Nodes/main/free_v2ray_xray_nodes.txt",
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub"
]

ENCRYPTION_KEY = "ODK-VPN-2026-SECRET-KEY"
ENABLE_ENCRYPTION = True
MAX_CONCURRENT_PROBES = 800  # 针对 3w 节点，提高并发海选
TOP_COUNT = 50               # 最终保留的最优节点数

# 精品地理规则：优先筛选物理距离近的顶级机房
GEO_RULES = {
    'HK': ['hk', 'hongkong', '香港', '港'],
    'TW': ['tw', 'taiwan', '台湾', '台'],
    'JP': ['jp', 'japan', '日本', '日', '东京', '大阪'],
    'SG': ['sg', 'singapore', '新加坡', '新'],
}
BLOCK_WORDS = ['us', 'america', '美国', 'uk', '英国', 'kr', '韩国']

# --- 工具函数 ---

def xor_encrypt(data: str, key: str) -> str:
    """保持原有的 XOR 加密逻辑"""
    data_bytes, key_bytes = data.encode('utf-8'), key.encode('utf-8')
    return base64.b64encode(bytearray(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data_bytes))).decode()

async def fetch_content(client, url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        res = await client.get(url, headers=headers, timeout=15.0)
        return res.text if res.status_code == 200 else ""
    except Exception:
        return ""

def get_node_target(link):
    """提取 (host, port) 用于测速"""
    try:
        protocol = link.split('://')[0]
        if protocol == 'vmess':
            decoded = base64.b64decode(link.split('://')[1]).decode('utf-8')
            config = json.loads(decoded)
            return config.get('add'), config.get('port')
        else:
            temp_link = link if '://' in link else f"http://{link}"
            parsed = urlparse(temp_link)
            return parsed.hostname, parsed.port or (443 if protocol in ['vless', 'trojan', 'hy2'] else 80)
    except:
        return None, None

async def probe_latency(semaphore, link):
    """精品探测：通过 3 轮探测计算稳定性评分"""
    host, port = get_node_target(link)
    if not host or not port:
        return None
    
    async with semaphore:
        latencies = []
        try:
            for _ in range(2): # 至少探测2轮确保不是偶尔通
                start_time = time.perf_counter()
                fut = asyncio.open_connection(host, int(port))
                reader, writer = await asyncio.wait_for(fut, timeout=1.2) # 严格超时：精品节点响应必须快
                latencies.append((time.perf_counter() - start_time) * 1000)
                writer.close()
                await writer.wait_closed()
            
            avg_lat = sum(latencies) / len(latencies)
            jitter = max(latencies) - min(latencies)
            # 综合分：延迟 + 抖动。抖动越小越稳
            return {"link": link, "latency": avg_lat, "score": avg_lat + (jitter * 2)}
        except:
            return None

# --- 主逻辑 ---

async def main():
    async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
        print(f"🛠️ 正在从 2026 全量源抓取并筛选精品节点...")
        raw_links = []
        
        # 1. 抓取与去重
        fetch_tasks = [fetch_content(client, url) for url in RAW_SOURCES]
        contents = await asyncio.gather(*fetch_tasks)
        
        for content in contents:
            if not content: continue
            if "://" not in content[:50]:
                try: content = base64.b64decode(content.strip()).decode('utf-8', errors='ignore')
                except: pass
            
            found = re.findall(r'(?:vmess|vless|trojan|ss|ssr|hy2|hysteria2)://[^\s|#|"\']+', content)
            raw_links.extend(found)

        unique_links = list(set(raw_links))
        print(f"📦 初始池: {len(unique_links)} 节点。")

        # 2. 地理前置过滤（只看港、日、台、新，大幅提升 3w 节点的处理速度）
        premium_candidates = []
        for l in unique_links:
            ps_lower = unquote(l).lower()
            if any(kw in ps_lower for kws in GEO_RULES.values() for kw in kws):
                premium_candidates.append(l)
        
        print(f"🎯 区域识别完成，候选精品: {len(premium_candidates)} 个。开始测速...")

        # 3. 并发探测
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_PROBES)
        tasks = [probe_latency(semaphore, link) for link in premium_candidates]
        results = await asyncio.gather(*tasks)
        
        # 4. 评分排序：按稳定性综合得分排序
        valid_results = sorted([r for r in results if r is not None], key=lambda x: x['score'])
        top_nodes_data = valid_results[:TOP_COUNT]

        # 5. 封装精品结果
        final_nodes = []
        for item in top_nodes_data:
            link = item['link']
            ps = unquote(link.split('#')[-1]) if '#' in link else f"Premium-Node"
            
            # 黑名单二次过滤
            if any(b in ps.lower() for b in BLOCK_WORDS): continue
            
            # 确定所属区域
            region = "UN"
            for code, kws in GEO_RULES.items():
                if any(kw in ps.lower() for kw in kws):
                    region = code
                    break
            
            final_nodes.append({
                'id': f'node_{hash(link)%1000000}',
                'name': f"💎 {ps}",
                'country': region,
                'latency': f"{int(item['latency'])}ms",
                'protocol': link.split('://')[0],
                'configUrl': link
            })

        # 6. 最终加密导出
        output_json = json.dumps(final_nodes, ensure_ascii=False, indent=2)
        result_payload = {
            "data": xor_encrypt(output_json, ENCRYPTION_KEY) if ENABLE_ENCRYPTION else base64.b64encode(output_json.encode()).decode(),
            "count": len(final_nodes),
            "timestamp": time.time(),
            "encrypted": ENABLE_ENCRYPTION
        }

        with open('nodes.json', 'w', encoding='utf-8') as f:
            json.dump(result_payload, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ 选拔完成！{len(final_nodes)} 个精品节点已存入 nodes.json (XOR加密)")
        if final_nodes:
            print(f"🚀 标杆节点: {final_nodes[0]['name']} | 延迟: {final_nodes[0]['latency']}")

if __name__ == "__main__":
    asyncio.run(main())