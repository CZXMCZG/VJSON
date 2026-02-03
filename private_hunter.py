import asyncio
import httpx
import base64
import re
import json
import random
import time
import socket
from urllib.parse import unquote, urlparse

# --- 核心配置 ---
RAW_SOURCES = [
    "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/main/all_extracted_configs.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/v2ray/all_sub.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Sub1.txt",
    "https://raw.githubusercontent.com/zipvpn/Free-V2Ray-Xray-Nodes/main/free_v2ray_xray_nodes.txt",
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub"
]

ENCRYPTION_KEY = "ODK-VPN-2026-SECRET-KEY"
ENABLE_ENCRYPTION = True
MAX_CONCURRENT_PROBES = 100  # 并发探测数，防止被封IP
TOP_COUNT = 50               # 最终保留的最优节点数

GEO_RULES = {
    'HK': ['hk', 'hongkong', '香港', '港'],
    'TW': ['tw', 'taiwan', '台湾', '台'],
    'JP': ['jp', 'japan', '日本', '日'],
    'SG': ['sg', 'singapore', '新加坡', '新'],
}
BLOCK_WORDS = ['us', 'america', '美国', 'uk', '英国', 'kr', '韩国']

# --- 工具函数 ---

def xor_encrypt(data: str, key: str) -> str:
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
    """从不同协议中提取 (host, port) 用于测速"""
    try:
        protocol = link.split('://')[0]
        if protocol == 'vmess':
            # vmess 链接是 base64 后的 json
            decoded = base64.b64decode(link.split('://')[1]).decode('utf-8')
            config = json.loads(decoded)
            return config.get('add'), config.get('port')
        else:
            # vless, trojan, ss 等遵循 URL 标准
            # 兼容处理非标准格式，临时替换协议头供 urlparse 识别
            temp_link = link if '://' in link else f"http://{link}"
            parsed = urlparse(temp_link)
            host = parsed.hostname
            port = parsed.port or (443 if protocol in ['vless', 'trojan', 'hy2'] else 80)
            return host, port
    except:
        return None, None

async def probe_latency(semaphore, link):
    """执行异步 TCP 握手测速"""
    host, port = get_node_target(link)
    if not host or not port:
        return None
    
    async with semaphore:
        start_time = time.perf_counter()
        try:
            # 建立 TCP 连接
            conn = asyncio.open_connection(host, int(port))
            reader, writer = await asyncio.wait_for(conn, timeout=2.5)
            latency = (time.perf_counter() - start_time) * 1000
            writer.close()
            await writer.wait_closed()
            return {"link": link, "latency": latency}
        except:
            return None

# --- 主逻辑 ---

async def main():
    async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
        print("🌐 正在从全球源抓取节点...")
        raw_links = []
        
        for url in RAW_SOURCES:
            content = await fetch_content(client, url)
            if not content: continue
            
            # 自动处理全文件 Base64 的情况
            if "://" not in content[:50]:
                try:
                    content = base64.b64decode(content.strip()).decode('utf-8', errors='ignore')
                except: pass
            
            found = re.findall(r'(?:vmess|vless|trojan|ss|ssr|hy2|hysteria2)://[^\s|#|"\']+', content)
            raw_links.extend(found)
            print(f" -> 提取到 {len(found)} 条来自 {url[-20:]}")

        unique_links = list(set(raw_links))
        print(f"\n⚡ 开始对 {len(unique_links)} 个节点进行并发测速...")

        # 并发控制
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_PROBES)
        tasks = [probe_latency(semaphore, link) for link in unique_links]
        
        # 执行测速并过滤掉超时节点
        results = await asyncio.gather(*tasks)
        valid_results = [r for r in results if r is not None]
        
        # 排序：取延迟最低的 TOP 50
        valid_results.sort(key=lambda x: x['latency'])
        top_nodes_data = valid_results[:TOP_COUNT]

        # 封装结果
        final_nodes = []
        for item in top_nodes_data:
            link = item['link']
            # 提取名称
            ps = unquote(link.split('#')[-1]) if '#' in link else f"Fast-Node-{random.randint(10,99)}"
            
            # 黑名单过滤
            if any(b in ps.lower() for b in BLOCK_WORDS): continue
            
            # 地理识别
            region = "UN"
            for code, kws in GEO_RULES.items():
                if any(kw in ps.lower() for kw in kws):
                    region = code
                    break
            
            final_nodes.append({
                'id': f'node_{hash(link)%1000000}',
                'name': ps,
                'country': region,
                'latency': f"{int(item['latency'])}ms",
                'protocol': link.split('://')[0],
                'configUrl': link
            })

        # 最终导出
        output_json = json.dumps(final_nodes, ensure_ascii=False, indent=2)
        result_payload = {
            "data": xor_encrypt(output_json, ENCRYPTION_KEY) if ENABLE_ENCRYPTION else base64.b64encode(output_json.encode()).decode(),
            "count": len(final_nodes),
            "timestamp": time.time(),
            "encrypted": ENABLE_ENCRYPTION
        }

        with open('nodes.json', 'w', encoding='utf-8') as f:
            json.dump(result_payload, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ 筛选完成！最优 {len(final_nodes)} 个节点已存入 nodes.json")
        if final_nodes:
            print(f"🚀 冠军节点: {final_nodes[0]['name']} | 延迟: {final_nodes[0]['latency']}")

if __name__ == "__main__":
    asyncio.run(main())