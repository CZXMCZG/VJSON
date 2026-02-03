import asyncio
import httpx
import base64
import re
import json
from urllib.parse import unquote
from typing import Dict, List, Optional

# --- 配置区 ---
# 升级源：加入聚合类高频更新源，这些源每天自动聚合数千个节点
HUNTER_SOURCES = [
    "https://raw.githubusercontent.com/freefq/free/master/v2",
    "https://raw.githubusercontent.com/vpei/free/master/v2ray",
    "https://raw.githubusercontent.com/mfuu/v2ray/master/v2ray",
    "https://raw.githubusercontent.com/Pawdroid/Free-nodes/main/node.txt",
    "https://raw.githubusercontent.com/Tiduxa/V2ray/master/V2ray",
    "https://raw.githubusercontent.com/ermaozi/get_node/main/subscribe/v2ray.txt",
    "https://raw.githubusercontent.com/mbelousov7/v2ray-nodes/main/nodes.txt"
]

ENCRYPTION_KEY = "ODK-VPN-2026-SECRET-KEY"
ENABLE_ENCRYPTION = True

# 严格白名单：只允许这四个 Code 导出
TARGET_REGIONS = ['HK', 'TW', 'JP', 'SG']

# 地理识别库：去掉 \b 限制，增强中英文包含判定
GEO_RULES = {
    'HK': ['hk', 'hongkong', 'hong kong', '香港', '港', '🇭🇰'],
    'TW': ['tw', 'taiwan', 'tai wan', '台湾', '台', '🇹🇼'],
    'JP': ['jp', 'japan', 'tokyo', 'osaka', '日本', '日', '东京', '大阪', '🇯🇵'],
    'SG': ['sg', 'singapore', '新加坡', '新', '狮城', '🇸🇬'],
}

BLOCK_WORDS = ['us', 'usa', 'america', '美国', '美', '🇺🇸', 'uk', '英国', '英', '🇬🇧', 'kr', 'korea', '韩国', '韩', '🇰🇷', 'de', 'germany', '德国', '德', '🇩🇪', 'ru', 'russia', '俄罗斯', '🇷🇺']

def xor_encrypt(data: str, key: str) -> str:
    data_bytes = data.encode('utf-8')
    key_bytes = key.encode('utf-8')
    result = bytearray()
    for i in range(len(data_bytes)):
        result.append(data_bytes[i] ^ key_bytes[i % len(key_bytes)])
    return base64.b64encode(result).decode('utf-8')

def get_region_code(ps: str, host: str) -> Optional[str]:
    """
    高精度地区识别：摒弃正则边界，采用逻辑包含判定
    """
    text = f"{ps} {host}".lower()

    # 1. 强效黑名单拦截
    for block in BLOCK_WORDS:
        if block.lower() in text:
            return None

    # 2. 白名单精准匹配
    for code, keywords in GEO_RULES.items():
        for kw in keywords:
            if kw.lower() in text:
                return code
    return None

def parse_vmess(url: str) -> Optional[Dict]:
    try:
        encoded = url.replace('vmess://', '').strip()
        missing_padding = len(encoded) % 4
        if missing_padding: encoded += '=' * (4 - missing_padding)
        
        decoded = base64.b64decode(encoded).decode('utf-8')
        config = json.loads(decoded)
        
        host = config.get('add', '')
        ps = config.get('ps', '')
        
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

def parse_generic(url: str, protocol: str) -> Optional[Dict]:
    """通用解析器，支持 trojan, vless, ss"""
    try:
        # 提取别名部分（#号后面）
        ps = ""
        if '#' in url:
            url_main, name_part = url.split('#', 1)
            ps = unquote(name_part).strip()
        else:
            url_main = url

        # 提取 host 部分（@符号后面，端口前面）
        host = ""
        host_match = re.search(r'@([^:/#\?\s]+)', url_main)
        if host_match:
            host = host_match.group(1)

        region = get_region_code(ps, host)
        if not region: return None

        # 提取端口
        port = "443"
        port_match = re.search(r':(\d+)', url_main.split('@')[-1])
        if port_match:
            port = port_match.group(1)

        return {
            'id': f'{protocol}_{hash(url) % 1000000}',
            'name': ps or f"{region}-{protocol.upper()}",
            'countryCode': region,
            'protocol': protocol,
            'configUrl': url,
            'config': {'add': host, 'port': port}
        }
    except: return None

async def check_latency(node: Dict) -> Optional[Dict]:
    try:
        host = node['config']['add']
        port = int(node['config']['port'])
        start = asyncio.get_event_loop().time()
        # 增加对 IP 地址格式的校验，防止无效 host 挂起
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=1.5)
        writer.close()
        await writer.wait_closed()
        node['latency'] = int((asyncio.get_event_loop().time() - start) * 1000)
        return node
    except: return None

async def main():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers=headers) as client:
        print("正在从多个强力源抓取...")
        raw_urls = []
        for url in HUNTER_SOURCES:
            try:
                res = await client.get(url)
                content = res.text
                
                # 深度解码逻辑：循环解码直到露出原形（处理多次 Base64 包装）
                for _ in range(3):
                    if "://" not in content[:100]:
                        try:
                            # 清洗数据，去除可能的空白符
                            content = base64.b64decode(content.strip()).decode('utf-8')
                        except: break
                    else: break
                
                # 强效正则：捕获几乎所有主流协议
                found = re.findall(r'(?:vmess|vless|trojan|ss|ssr)://[^\s|#|"]+', content)
                raw_urls.extend(found)
            except: continue

        # 1. 解析与过滤
        parsed_nodes = []
        for u in list(set(raw_urls)):
            node = None
            if u.startswith('vmess://'):
                node = parse_vmess(u)
            else:
                proto = u.split('://')[0]
                node = parse_generic(u, proto)
            
            if node: parsed_nodes.append(node)
        
        print(f"识别到目标地区节点: {len(parsed_nodes)} 个，开始并行测速...")

        # 2. 测速（控制并发防止死锁）
        tasks = [check_latency(n) for n in parsed_nodes]
        results = await asyncio.gather(*tasks)
        valid_nodes = [r for r in results if r]
        
        # 3. 排序与截取
        valid_nodes.sort(key=lambda x: x['latency'])
        final_list = valid_nodes[:100] # 扩大到100个，保证质量

        # 4. 导出格式保持一致
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