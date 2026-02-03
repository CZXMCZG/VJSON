import asyncio
import httpx
import base64
import re
import json
import random
import time
from urllib.parse import unquote, quote

# --- 核心配置：换用 2026 极其稳定的全量源 ---
RAW_SOURCES = [
    "https://raw.githubusercontent.com/tiamm/free-nodes/main/nodes.txt",
    "https://raw.githubusercontent.com/vfarid/v2ray-worker-sub/master/sub/vless",
    "https://raw.githubusercontent.com/mahdibland/V2RayAggregator/master/E900/all",
    "https://raw.githubusercontent.com/Leon406/SubCrawler/main/sub/share/v2",
    "https://raw.githubusercontent.com/ripaojiedian/freenode/main/sub"
]

ENCRYPTION_KEY = "ODK-VPN-2026-SECRET-KEY"
ENABLE_ENCRYPTION = True

# 扩展地理识别关键词
GEO_RULES = {
    'HK': ['hk', 'hongkong', '香港', '港', '广港', '沪港', '深港', 'IEPL', 'CN2', 'HGC'],
    'TW': ['tw', 'taiwan', '台湾', '台', 'CHT', '🇹🇼'],
    'JP': ['jp', 'japan', '日本', '日', '东京', '大阪'],
    'SG': ['sg', 'singapore', '新加坡', '新', '狮城'],
}
# 缩小黑名单，仅过滤确定不想要的，且采用全词匹配防止误伤（如 hk-us 不应被删）
BLOCK_WORDS = ['🇺🇸', '美国', '英国', '韩国', 'russia'] 

async def fetch_content(client, url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    try:
        res = await client.get(url, headers=headers, timeout=20.0)
        return res.text if res.status_code == 200 else ""
    except:
        return ""

def xor_encrypt(data: str, key: str) -> str:
    data_bytes, key_bytes = data.encode('utf-8'), key.encode('utf-8')
    return base64.b64encode(bytearray(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data_bytes))).decode()

async def main():
    async with httpx.AsyncClient(follow_redirects=True, verify=False) as client:
        print("🔍 正在执行宽松地理过滤抓取...")
        all_raw_links = []
        
        for url in RAW_SOURCES:
            content = await fetch_content(client, url)
            if not content: continue
            
            # 暴力处理：先尝试解密整页 Base64
            if "://" not in content[:50]:
                try:
                    content = base64.b64decode(content.strip()).decode('utf-8', errors='ignore')
                except: pass
            
            # 正则提取
            found = re.findall(r'(?:vmess|vless|trojan|ss|ssr|hy2|hysteria2)://[^\s|#|"\']+', content)
            all_raw_links.extend(found)
            print(f"从源 {url[-15:]} 提取到 {len(found)} 个候选节点")

        parsed_nodes = []
        for link in list(set(all_raw_links)):
            # 提取名称
            ps = unquote(link.split('#')[-1]).lower() if '#' in link else "fast-node"
            
            # 1. 黑名单初筛（仅剔除极其明确的）
            if any(b in ps for b in BLOCK_WORDS):
                continue
            
            # 2. 地理识别（如果匹配不到，标记为 Global 而不是丢弃）
            region = "Global"
            for code, kws in GEO_RULES.items():
                if any(kw.lower() in ps for kw in kws):
                    region = code
                    break
            
            # 3. 构造节点
            parsed_nodes.append({
                'id': f'node_{hash(link)%1000000}',
                'name': ps.upper(),
                'country': region,
                'countryCode': region,
                'protocol': link.split('://')[0],
                'configUrl': link,
                'config': {'add': 'auto', 'port': '443'}
            })

        # 按地区排序，把港台排在前面
        parsed_nodes.sort(key=lambda x: (x['countryCode'] not in ['HK', 'TW'], x['countryCode']))

        output = {
            "data": xor_encrypt(json.dumps(parsed_nodes, ensure_ascii=False), ENCRYPTION_KEY) if ENABLE_ENCRYPTION else base64.b64encode(json.dumps(parsed_nodes, ensure_ascii=False).encode()).decode(),
            "count": len(parsed_nodes),
            "timestamp": str(time.time()),
            "encrypted": ENABLE_ENCRYPTION
        }
        
        with open('nodes.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ 抓取成功！")
        print(f"总计节点: {len(parsed_nodes)}")
        print(f"其中香港(HK): {len([n for n in parsed_nodes if n['countryCode']=='HK'])} 个")
        print(f"其中台湾(TW): {len([n for n in parsed_nodes if n['countryCode']=='TW'])} 个")

if __name__ == "__main__":
    asyncio.run(main())