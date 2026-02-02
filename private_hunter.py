import asyncio
import httpx
import base64
import re
import json
from urllib.parse import unquote
from typing import Dict, List, Optional

# --- 配置区 ---
HUNTER_SOURCES = [
    "https://raw.githubusercontent.com/freefq/free/master/v2",
    "https://raw.githubusercontent.com/zufuli/proxypool/master/proxypool/resources/sources.txt",
    "https://raw.githubusercontent.com/vpei/free/master/v2ray",
    "https://api.kkss.pw/subscribe?collector=github",
    "https://raw.githubusercontent.com/Pawdroid/Free-nodes/main/node.txt",
    "https://raw.githubusercontent.com/mfuu/v2ray/master/v2ray"
]

ENCRYPTION_KEY = "ODK-VPN-2026-SECRET-KEY"
ENABLE_ENCRYPTION = True

# 严格白名单：只允许这四个 Code 导出
TARGET_REGIONS = ['HK', 'TW', 'JP', 'SG']

# 地理识别库：增加黑名单拦截和中英文精准匹配
GEO_RULES = {
    'HK': ['hk', 'hongkong', 'hong kong', '香港', '港', '🇭🇰'],
    'TW': ['tw', 'taiwan', 'tai wan', '台湾', '台', '🇹🇼'],
    'JP': ['jp', 'japan', 'tokyo', 'osaka', '日本', '日', '东京', '大阪', '🇯🇵'],
    'SG': ['sg', 'singapore', '新加坡', '新', '狮城', '🇸🇬'],
}

# 强效黑名单：只要包含这些词，哪怕有 HK 关键词也直接剔除
BLOCK_WORDS = ['us', 'usa', 'united states', 'america', '美国', '美', '🇺🇸', 
               'uk', 'united kingdom', '英国', '英', '🇬🇧',
               'kr', 'korea', '韩国', '韩', '🇰🇷',
               'de', 'germany', '德国', '德', '🇩🇪',
               'ru', 'russia', '俄罗斯', '🇷🇺']

def xor_encrypt(data: str, key: str) -> str:
    data_bytes = data.encode('utf-8')
    key_bytes = key.encode('utf-8')
    result = bytearray()
    for i in range(len(data_bytes)):
        result.append(data_bytes[i] ^ key_bytes[i % len(key_bytes)])
    return base64.b64encode(result).decode('utf-8')

def get_region_code(ps: str, host: str) -> Optional[str]:
    """
    高精度地区识别引擎
    """
    text = f"{ps} {host}".lower()

    # 1. 强效黑名单拦截：防止 US-HK 这种混合命名的节点混入
    for block in BLOCK_WORDS:
        # \b 匹配独立单词，防止误杀域名里的字母
        if re.search(r'\b' + re.escape(block) + r'\b', text) or block in text:
            # 如果包含黑名单词，直接判定无效
            return None

    # 2. 白名单精准匹配
    for code, keywords in GEO_RULES.items():
        for kw in keywords:
            # 匹配逻辑：独立单词 或 中文字符直接包含
            if re.search(r'\b' + re.escape(kw) + r'\b', text) or (re.search(r'[\u4e00-\u9fa5]', kw) and kw in text):
                return code
    
    return None

def parse_vmess(url: str) -> Optional[Dict]:
    try:
        encoded = url.replace('vmess://', '')
        # 补齐 base64 填充
        missing_padding = len(encoded) % 4
        if missing_padding: encoded += '=' * (4 - missing_padding)
        
        decoded = base64.b64decode(encoded).decode('utf-8')
        config = json.loads(decoded)
        
        host = config.get('add', '')
        ps = config.get('ps', '')
        
        # 核心过滤：识别不到指定地区的直接丢弃
        region = get_region_code(ps, host)
        if not region: return None

        return {
            'id': f'vmess_{hash(url) % 1000000}',
            'name': ps or f"{region}-VMESS",
            'countryCode': region,
            'protocol': 'vmess',
            'configUrl': url,
            'config': {
                'add': host, 'port': str(config.get('port', 443)),
                'id': config.get('id', ''), 'net': config.get('net', 'tcp'),
                'tls': config.get('tls', ''), 'path': config.get('path', '/')
            }
        }
    except: return None

def parse_trojan(url: str) -> Optional[Dict]:
    try:
        match = re.match(r'trojan://([^@]+)@([^:]+):(\d+)(\?[^#]*)?(#(.*))?', url)
        if not match: return None
        _, host, port, _, _, name = match.groups()
        ps = unquote(name) if name else ""
        
        region = get_region_code(ps, host)
        if not region: return None

        return {
            'id': f'trojan_{hash(url) % 1000000}',
            'name': ps or f"{region}-TROJAN",
            'countryCode': region,
            'protocol': 'trojan',
            'configUrl': url,
            'config': {'add': host, 'port': port}
        }
    except: return None

async def check_latency(node: Dict) -> Optional[Dict]:
    try:
        host = node['config']['add']
        port = int(node['config']['port'])
        start = asyncio.get_event_loop().time()
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=2.0)
        writer.close()
        await writer.wait_closed()
        node['latency'] = int((asyncio.get_event_loop().time() - start) * 1000)
        return node
    except: return None

async def main():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers=headers) as client:
        print("正在抓取源...")
        raw_urls = []
        for url in HUNTER_SOURCES:
            try:
                res = await client.get(url)
                content = res.text
                if "://" not in content[:50]:
                    try: content = base64.b64decode(content).decode('utf-8')
                    except: pass
                raw_urls.extend(re.findall(r'(?:vmess|trojan)://[^\s]+', content))
            except: continue

        # 1. 唯一化并解析（执行地区过滤）
        parsed_nodes = []
        for u in list(set(raw_urls)):
            node = parse_vmess(u) if u.startswith('vmess://') else parse_trojan(u)
            if node: parsed_nodes.append(node)
        
        print(f"解析到目标地区节点: {len(parsed_nodes)} 个，开始测速...")

        # 2. 测速
        tasks = [check_latency(n) for n in parsed_nodes]
        results = await asyncio.gather(*tasks)
        valid_nodes = [r for r in results if r]
        
        # 3. 排序截取前 50
        valid_nodes.sort(key=lambda x: x['latency'])
        final_list = valid_nodes[:50]

        # 4. 导出
        json_data = json.dumps(final_list, ensure_ascii=False)
        output = {
            "data": xor_encrypt(json_data, ENCRYPTION_KEY) if ENABLE_ENCRYPTION else base64.b64encode(json_data.encode()).decode(),
            "count": len(final_list),
            "timestamp": str(asyncio.get_event_loop().time())
        }
        
        with open('nodes.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"成功导出 {len(final_list)} 个节点到 nodes.json")

if __name__ == "__main__":
    asyncio.run(main())