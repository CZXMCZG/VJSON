import asyncio
import httpx
import base64
import re
import json
import random
import time
from urllib.parse import unquote, quote

# --- 核心配置：换用 2026 最稳聚合源 ---
RAW_SOURCES = [
    "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/main/all_extracted_configs.txt",
    "https://raw.githubusercontent.com/MatinGhanbari/v2ray-configs/main/subscriptions/v2ray/all_sub.txt",
    "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Sub1.txt",
    "https://raw.githubusercontent.com/zipvpn/Free-V2Ray-Xray-Nodes/main/free_v2ray_xray_nodes.txt",
    "https://raw.githubusercontent.com/Pawdroid/Free-servers/main/sub"
]

ENCRYPTION_KEY = "ODK-VPN-2026-SECRET-KEY"
ENABLE_ENCRYPTION = True

# 地理识别保持不变，但增加默认识别
GEO_RULES = {
    'HK': ['hk', 'hongkong', '香港', '港'],
    'TW': ['tw', 'taiwan', '台湾', '台'],
    'JP': ['jp', 'japan', '日本', '日'],
    'SG': ['sg', 'singapore', '新加坡', '新'],
}
BLOCK_WORDS = ['us', 'america', '美国', 'uk', '英国', 'kr', '韩国']

async def fetch_content(client, url):
    """暴力抓取：忽略证书，伪造高真实度 UA"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }
    try:
        # 使用直连，不再通过 jsdelivr 绕路（镜像有时会缓存空内容）
        res = await client.get(url, headers=headers, timeout=20.0)
        if res.status_code == 200:
            return res.text
    except Exception as e:
        print(f"抓取失败 {url}: {e}")
    return ""

def xor_encrypt(data: str, key: str) -> str:
    data_bytes, key_bytes = data.encode('utf-8'), key.encode('utf-8')
    return base64.b64encode(bytearray(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data_bytes))).decode()

async def main():
    # verify=False 彻底解决 SSL 握手失败问题
    async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
        print("🛠️ 正在执行强制抓取逻辑...")
        raw_links = []
        
        for url in RAW_SOURCES:
            content = await fetch_content(client, url)
            if not content: continue
            
            # 第一步：尝试 Base64 全解（针对整个文件是加密的情况）
            if "://" not in content[:50]:
                try:
                    content = base64.b64decode(content.strip()).decode('utf-8', errors='ignore')
                except: pass
            
            # 第二步：暴力正则匹配（不分协议，通杀提取）
            found = re.findall(r'(?:vmess|vless|trojan|ss|ssr|hy2|hysteria2)://[^\s|#|"\']+', content)
            raw_links.extend(found)
            print(f"从 {url[-20:]} 提取到 {len(found)} 条原始链接")

        # 去重并构建最终节点
        final_nodes = []
        for link in list(set(raw_links)):
            # 极简解析逻辑，保证不死机
            ps = unquote(link.split('#')[-1]) if '#' in link else f"Node-{random.randint(100,999)}"
            
            # 黑名单粗筛
            if any(b in ps.lower() for b in BLOCK_WORDS): continue
            
            # 区域判定
            region = "UN"
            for code, kws in GEO_RULES.items():
                if any(kw in ps.lower() for kw in kws):
                    region = code
                    break
            
            final_nodes.append({
                'id': f'node_{hash(link)%1000000}',
                'name': ps,
                'country': region,
                'countryCode': region,
                'protocol': link.split('://')[0],
                'configUrl': link,
                'config': {'add': 'auto', 'port': '443'}
            })

        # 导出结果
        output = {
            "data": xor_encrypt(json.dumps(final_nodes, ensure_ascii=False), ENCRYPTION_KEY) if ENABLE_ENCRYPTION else base64.b64encode(json.dumps(final_nodes, ensure_ascii=False).encode()).decode(),
            "count": len(final_nodes),
            "timestamp": str(time.time()),
            "encrypted": ENABLE_ENCRYPTION
        }
        
        with open('nodes.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ 任务完成！共计有效节点: {len(final_nodes)}")
        print(f"数据已导出至 nodes.json，请检查文件大小。")

if __name__ == "__main__":
    asyncio.run(main())