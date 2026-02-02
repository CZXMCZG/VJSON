import asyncio
import httpx
import base64
import re
import json
import os
from urllib.parse import urlparse, parse_qs, unquote
from typing import Dict, List, Optional

# 节点来源
HUNTER_SOURCES = [
    "https://raw.githubusercontent.com/freefq/free/master/v2",
    "https://raw.githubusercontent.com/zufuli/proxypool/master/proxypool/resources/sources.txt",
    "https://raw.githubusercontent.com/vpei/free/master/v2ray",
    "https://api.kkss.pw/subscribe?collector=github",
    "https://raw.githubusercontent.com/Pawdroid/Free-nodes/main/node.txt",
    "https://raw.githubusercontent.com/mfuu/v2ray/master/v2ray"
]

# 加密配置
ENCRYPTION_KEY = "ODK-VPN-2026-SECRET-KEY"
ENABLE_ENCRYPTION = True

# 目标地区白名单（只有匹配到这些才保留）
TARGET_REGIONS = ['HK', 'TW', 'JP', 'SG']

# 增强版地理位置映射（增加排除名单以提高过滤准确度）
LOCATION_MAP = {
    'HK': {'keywords': ['hk', 'hongkong', 'hong kong', '香港', '港'], 'name': '香港'},
    'TW': {'keywords': ['tw', 'taiwan', 'tai wan', '台湾', '台'], 'name': '台湾'},
    'JP': {'keywords': ['jp', 'japan', 'tokyo', 'osaka', '日本', '日', '东京', '大阪'], 'name': '日本'},
    'SG': {'keywords': ['sg', 'singapore', '新加坡', '新', '狮城'], 'name': '新加坡'},
    # 显式定义的黑名单（匹配到这些直接打上排除标记）
    'US': {'keywords': ['us', 'united states', 'america', 'usa', '美国', '美'], 'name': '美国'},
    'UK': {'keywords': ['uk', 'united kingdom', 'britain', '英国', '英'], 'name': '英国'},
    'KR': {'keywords': ['kr', 'korea', 'seoul', '韩国', '韩', '首尔'], 'name': '韩国'},
}

# 云服务商识别
CLOUD_PROVIDERS = {
    'aws': 'Amazon AWS',
    'azure': 'Microsoft Azure',
    'oracle': 'Oracle Cloud',
    'google': 'Google Cloud',
    'digitalocean': 'DigitalOcean',
    'vultr': 'Vultr',
    'linode': 'Linode',
    'cloudflare': 'Cloudflare',
}

def xor_encrypt(data: str, key: str) -> str:
    """XOR加密"""
    data_bytes = data.encode('utf-8')
    key_bytes = key.encode('utf-8')
    result = bytearray()
    for i in range(len(data_bytes)):
        result.append(data_bytes[i] ^ key_bytes[i % len(key_bytes)])
    return base64.b64encode(result).decode('utf-8')

def guess_location(ps_name: str, host: str) -> Dict[str, str]:
    """
    改进的地理位置推测：
    1. 备注名(ps)优先级最高
    2. 使用正则单词边界匹配，防止误判
    3. 只要不在 TARGET_REGIONS 内，统一返回 OTHER
    """
    search_text = f"{ps_name} {host}".lower()
    
    # 按照目标地区循环匹配
    for code, info in LOCATION_MAP.items():
        for kw in info['keywords']:
            # 使用正则 \b 匹配独立单词或中文关键词直接匹配
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, search_text) or (re.search(r'[\u4e00-\u9fa5]', kw) and kw in search_text):
                return {'country': info['name'], 'countryCode': code}
    
    return {'country': 'Other', 'countryCode': 'OTHER'}

def detect_provider(host: str) -> Optional[str]:
    """检测云服务商"""
    host_lower = host.lower()
    for keyword, provider in CLOUD_PROVIDERS.items():
        if keyword in host_lower: return provider
    return None

def parse_vmess(url: str) -> Optional[Dict]:
    """解析VMESS节点"""
    try:
        encoded = url.replace('vmess://', '')
        decoded = base64.b64decode(encoded).decode('utf-8')
        config = json.loads(decoded)
        
        host = config.get('add', config.get('host', ''))
        name = config.get('ps', config.get('remarks', ''))
        
        # 严格过滤地区
        location = guess_location(name, host)
        if location['countryCode'] not in TARGET_REGIONS:
            return None
        
        provider = detect_provider(host)
        return {
            'id': f'vmess_{hash(url) % 1000000}',
            'name': name or f"VMESS-{location['country']}",
            'country': location['country'],
            'countryCode': location['countryCode'],
            'protocol': 'vmess',
            'configUrl': url,
            'config': {
                'add': host, 'port': str(config.get('port', 443)),
                'id': config.get('id', ''), 'aid': str(config.get('aid', 0)),
                'net': config.get('net', 'tcp'), 'tls': config.get('tls', ''),
                'path': config.get('path', '/'), 'sni': config.get('sni', '')
            },
            'provider': provider,
            'isPremium': provider is not None,
            'tags': ['hunter', 'vmess'],
        }
    except: return None

def parse_trojan(url: str) -> Optional[Dict]:
    """解析TROJAN节点"""
    try:
        match = re.match(r'trojan://([^@]+)@([^:]+):(\d+)(\?[^#]*)?(#(.*))?', url)
        if not match: return None
        password, host, port, params, _, name = match.groups()
        name = unquote(name) if name else ""
        
        location = guess_location(name, host)
        if location['countryCode'] not in TARGET_REGIONS: return None
        
        provider = detect_provider(host)
        return {
            'id': f'trojan_{hash(url) % 1000000}',
            'name': name or f"TROJAN-{location['country']}",
            'country': location['country'],
            'countryCode': location['countryCode'],
            'protocol': 'trojan',
            'configUrl': url,
            'config': {'add': host, 'port': port, 'password': password},
            'provider': provider,
            'isPremium': provider is not None,
            'tags': ['hunter', 'trojan'],
        }
    except: return None

def parse_node(url: str) -> Optional[Dict]:
    """解析节点入口"""
    if url.startswith('vmess://'): return parse_vmess(url)
    if url.startswith('trojan://'): return parse_trojan(url)
    # VLESS 和 SS 的逻辑同理，需确保内部调用 guess_location 并拦截非目标地区
    return None

async def check_node_quality(node_data: Dict) -> Optional[Dict]:
    """检查节点连接性"""
    try:
        config = node_data['config']
        host = config.get('add', config.get('host', ''))
        port = int(config.get('port', 443))
        
        start = asyncio.get_event_loop().time()
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=2.5)
        writer.close()
        await writer.wait_closed()
        
        latency = int((asyncio.get_event_loop().time() - start) * 1000)
        node_data['latency'] = latency
        # 简易评分逻辑
        node_data['score'] = max(0.1, 1.0 - (latency / 2500)) 
        return node_data
    except: return None

async def main():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
        all_content = ""
        for url in HUNTER_SOURCES:
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    text = r.text
                    # 自动处理Base64订阅格式
                    if "://" not in text[:50]:
                        try: text = base64.b64decode(text).decode('utf-8')
                        except: pass
                    all_content += text + "\n"
            except: continue
        
        node_urls = list(set(re.findall(r'(?:vmess|trojan)://[^\s]+', all_content)))
        if not node_urls: return

        # 解析并过滤地区
        parsed_nodes = [n for n in [parse_node(u) for u in node_urls] if n]
        
        # 质量检测
        tasks = [check_node_quality(node) for node in parsed_nodes]
        results = await asyncio.gather(*tasks)
        valid_nodes = [r for r in results if r]
        
        # 排序并截取
        valid_nodes.sort(key=lambda x: (-x['isPremium'], x['latency']))
        final_nodes = valid_nodes[:50]
        
        # 准备输出
        output = {
            "data": xor_encrypt(json.dumps(final_nodes, ensure_ascii=False), ENCRYPTION_KEY) if ENABLE_ENCRYPTION else base64.b64encode(json.dumps(final_nodes).encode()).decode(),
            "timestamp": str(asyncio.get_event_loop().time()),
            "count": len(final_nodes),
            "encrypted": ENABLE_ENCRYPTION,
            "stats": {
                "by_country": {c: sum(1 for n in final_nodes if n['countryCode'] == c) for c in TARGET_REGIONS}
            }
        }
        
        with open('nodes.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"爬取完成，有效节点数: {len(final_nodes)}")

if __name__ == "__main__":
    asyncio.run(main())