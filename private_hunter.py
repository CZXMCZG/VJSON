import asyncio
import httpx
import base64
import re
import json
import random
import time
from urllib.parse import unquote, quote
from typing import Dict, List, Optional

# --- 防封配置区 ---
def mirror_url(url: str) -> str:
    if "raw.githubusercontent.com" in url:
        parts = url.replace("https://raw.githubusercontent.com/", "").split("/")
        if len(parts) >= 3:
            user, repo, branch = parts[0], parts[1], parts[2]
            path = "/".join(parts[3:])
            return f"https://fastly.jsdelivr.net/gh/{user}/{repo}@{branch}/{path}"
    return url

# 更新为 2026 年高频活跃源
RAW_SOURCES = [
    "https://raw.githubusercontent.com/barry-far/V2ray-config/main/Sub1.txt",
    "https://raw.githubusercontent.com/ebrasha/free-v2ray-public-list/main/V2Ray-Config-By-EbraSha-All-Type.txt",
    "https://raw.githubusercontent.com/vfarid/v2ray-worker-sub/master/sub/vless",
    "https://raw.githubusercontent.com/ripaojiedian/freenode/main/sub",
    "https://raw.githubusercontent.com/snakem982/proxypool/main/source/all.txt"
]

HUNTER_SOURCES = [mirror_url(url) for url in RAW_SOURCES]
ENCRYPTION_KEY = "ODK-VPN-2026-SECRET-KEY"
ENABLE_ENCRYPTION = True

GEO_RULES = {
    'HK': ['hk', 'hongkong', '香港', '港', '广港', '沪港', '深港', 'IEPL'],
    'TW': ['tw', 'taiwan', '台湾', '台', '🇹🇼'],
    'JP': ['jp', 'japan', 'tokyo', '日本', '日', '🇯🇵'],
    'SG': ['sg', 'singapore', '新加坡', '新', '🇸🇬'],
}

BLOCK_WORDS = ['us', 'america', '美国', 'uk', '英国', 'kr', '韩国', 'de', '德国', 'ru', '俄罗斯']

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1"
]

def xor_encrypt(data: str, key: str) -> str:
    data_bytes, key_bytes = data.encode('utf-8'), key.encode('utf-8')
    result = bytearray(b1 ^ key_bytes[i % len(key_bytes)] for i, b1 in enumerate(data_bytes))
    return base64.b64encode(result).decode('utf-8')

async def fetch_with_retry(client, url):
    for i in range(3):
        try:
            await asyncio.sleep(random.uniform(0.5, 1.5))
            headers = {"User-Agent": random.choice(UA_POOL)}
            res = await client.get(url, headers=headers, timeout=15.0)
            if res.status_code == 200:
                return res.text
        except:
            continue
    return ""

def get_region_code(ps: str, url_context: str) -> str:
    text = f"{ps} {url_context}".lower()
    for code, keywords in GEO_RULES.items():
        if any(kw.lower() in text for kw in keywords):
            return code
    return "Global" # 无法识别地区时兜底，不删除

async def main():
    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0, verify=False) as client:
        print("🚀 启动万能抓取模式 (降级容错版)...")
        raw_urls = []
        
        for url in HUNTER_SOURCES:
            content = await fetch_with_retry(client, url)
            if not content or len(content) < 10:
                continue
            
            # --- 自动处理 Base64 页面 ---
            effective_content = content
            if "://" not in content[:100]:
                try:
                    decoded = base64.b64decode(content.strip()).decode('utf-8', errors='ignore')
                    effective_content = decoded
                except:
                    pass

            # --- 宽松正则提取 ---
            found = re.findall(r'(?:vmess|vless|trojan|ss|ssr|hysteria2|hy2)://[^\s|#|"\']+', effective_content)
            raw_urls.extend(found)
            
            # --- 探测订阅链 ---
            subs = re.findall(r'https?://[^\s\'"]+(?:sub|subscribe|link|token=)[^\s\'"]+', effective_content)
            for s in subs[:3]:
                conv_url = f"https://api.v1.mk/sub?target=v2ray&url={quote(s)}"
                sub_content = await fetch_with_retry(client, conv_url)
                if sub_content:
                    try:
                        decoded_sub = base64.b64decode(sub_content).decode('utf-8', errors='ignore')
                        raw_urls.extend(re.findall(r'(?:vmess|vless|trojan|ss|ssr)://[^\s|#|"\']+', decoded_sub))
                    except:
                        raw_urls.extend(re.findall(r'(?:vmess|vless|trojan|ss|ssr)://[^\s|#|"\']+', sub_content))
        
        # 去重
        unique_links = list(set(raw_urls))
        parsed_nodes = []
        
        for u in unique_links:
            # 基础信息提取
            proto = u.split('://')[0]
            ps = unquote(u.split('#')[-1]) if '#' in u else f"{proto.upper()}-NODE-{random.randint(1000, 9999)}"
            
            # 黑名单过滤（仅过滤明确禁止的地区）
            if any(block in ps.lower() for block in BLOCK_WORDS):
                continue
            
            region = get_region_code(ps, u)
            
            # 构造标准化节点对象
            node = {
                'id': f'node_{hash(u) % 1000000}',
                'name': ps,
                'country': region,
                'countryCode': region,
                'protocol': proto,
                'configUrl': u,
                'config': {
                    'add': 'auto-extracted',
                    'port': '443',
                    'id': 'none'
                }
            }
            parsed_nodes.append(node)
        
        print(f"📊 扫描完成：共发现 {len(unique_links)} 条原始数据")
        print(f"✅ 有效入库：{len(parsed_nodes)} 个节点")
        
        # 导出结果
        output_data = json.dumps(parsed_nodes, ensure_ascii=False)
        final_payload = xor_encrypt(output_data, ENCRYPTION_KEY) if ENABLE_ENCRYPTION else base64.b64encode(output_data.encode()).decode()
        
        output = {
            "data": final_payload,
            "count": len(parsed_nodes),
            "timestamp": str(time.time()),
            "encrypted": ENABLE_ENCRYPTION,
            "version": "3.0"
        }
        
        with open('nodes.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        print(f"🎉 任务成功，数据已加密写入 nodes.json")

if __name__ == "__main__":
    asyncio.run(main())