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

# 目标地区（只爬取这些地区的节点）
TARGET_REGIONS = ['HK', 'TW', 'JP', 'SG']  # 香港、台湾、日本、新加坡

# 地理位置映射
LOCATION_KEYWORDS = {
    'hk': {'country': '香港', 'countryCode': 'HK'},
    'hongkong': {'country': '香港', 'countryCode': 'HK'},
    'hong kong': {'country': '香港', 'countryCode': 'HK'},
    'tw': {'country': '台湾', 'countryCode': 'TW'},
    'taiwan': {'country': '台湾', 'countryCode': 'TW'},
    'sg': {'country': '新加坡', 'countryCode': 'SG'},
    'singapore': {'country': '新加坡', 'countryCode': 'SG'},
    'jp': {'country': '日本', 'countryCode': 'JP'},
    'japan': {'country': '日本', 'countryCode': 'JP'},
}

# 云服务商识别
CLOUD_PROVIDERS = {
    'aws': 'Amazon AWS',
    'amazon': 'Amazon AWS',
    'ec2': 'Amazon AWS',
    'azure': 'Microsoft Azure',
    'microsoft': 'Microsoft Azure',
    'oracle': 'Oracle Cloud',
    'oci': 'Oracle Cloud',
    'google': 'Google Cloud',
    'gcp': 'Google Cloud',
    'googlecloud': 'Google Cloud',
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


def guess_location(text: str) -> Dict[str, str]:
    """从文本中推测地理位置"""
    text_lower = text.lower()
    
    for keyword, location in LOCATION_KEYWORDS.items():
        if keyword in text_lower:
            return location
    
    return {'country': 'Unknown', 'countryCode': 'XX'}


def detect_provider(host: str) -> Optional[str]:
    """检测云服务商"""
    host_lower = host.lower()
    
    for keyword, provider in CLOUD_PROVIDERS.items():
        if keyword in host_lower:
            return provider
    
    return None


def parse_vmess(url: str) -> Optional[Dict]:
    """解析VMESS节点"""
    try:
        # 移除 vmess:// 前缀
        encoded = url.replace('vmess://', '')
        # Base64解码
        decoded = base64.b64decode(encoded).decode('utf-8')
        config = json.loads(decoded)
        
        host = config.get('add', config.get('host', ''))
        port = config.get('port', 443)
        name = config.get('ps', config.get('remarks', f'VMESS-{host}'))
        
        # 推测地理位置
        location = guess_location(name + ' ' + host)
        
        # 只保留目标地区的节点
        if location['countryCode'] not in TARGET_REGIONS:
            return None
        
        # 检测提供商
        provider = detect_provider(host)
        is_premium = provider is not None
        
        return {
            'id': f'vmess_{hash(url) % 1000000}',
            'name': name,
            'country': location['country'],
            'countryCode': location['countryCode'],
            'protocol': 'vmess',
            'configUrl': url,
            'config': {
                'add': host,
                'host': host,
                'port': str(port),
                'id': config.get('id', ''),
                'aid': str(config.get('aid', 0)),
                'net': config.get('net', 'tcp'),
                'type': config.get('type', 'none'),
                'tls': config.get('tls', ''),
                'sni': config.get('sni', ''),
                'path': config.get('path', '/'),
            },
            'provider': provider,
            'isPremium': is_premium,
            'tags': ['hunter', 'vmess'],
        }
    except:
        return None


def parse_trojan(url: str) -> Optional[Dict]:
    """解析TROJAN节点"""
    try:
        # trojan://password@host:port?params#name
        match = re.match(r'trojan://([^@]+)@([^:]+):(\d+)(\?[^#]*)?(#(.*))?', url)
        if not match:
            return None
        
        password, host, port, params, _, name = match.groups()
        name = unquote(name) if name else f'TROJAN-{host}'
        
        # 推测地理位置
        location = guess_location(name + ' ' + host)
        
        # 只保留目标地区的节点
        if location['countryCode'] not in TARGET_REGIONS:
            return None
        
        # 检测提供商
        provider = detect_provider(host)
        is_premium = provider is not None
        
        # 解析参数
        config = {
            'add': host,
            'host': host,
            'port': port,
            'password': password,
        }
        
        if params:
            params_dict = parse_qs(params[1:])  # 移除 ?
            config.update({
                'sni': params_dict.get('sni', [host])[0],
                'type': params_dict.get('type', ['tcp'])[0],
                'security': params_dict.get('security', ['tls'])[0],
            })
        
        return {
            'id': f'trojan_{hash(url) % 1000000}',
            'name': name,
            'country': location['country'],
            'countryCode': location['countryCode'],
            'protocol': 'trojan',
            'configUrl': url,
            'config': config,
            'provider': provider,
            'isPremium': is_premium,
            'tags': ['hunter', 'trojan'],
        }
    except:
        return None


def parse_vless(url: str) -> Optional[Dict]:
    """解析VLESS节点"""
    try:
        # vless://uuid@host:port?params#name
        match = re.match(r'vless://([^@]+)@([^:]+):(\d+)(\?[^#]*)?(#(.*))?', url)
        if not match:
            return None
        
        uuid, host, port, params, _, name = match.groups()
        name = unquote(name) if name else f'VLESS-{host}'
        
        # 推测地理位置
        location = guess_location(name + ' ' + host)
        
        # 只保留目标地区的节点
        if location['countryCode'] not in TARGET_REGIONS:
            return None
        
        # 检测提供商
        provider = detect_provider(host)
        is_premium = provider is not None
        
        # 解析参数
        config = {
            'add': host,
            'host': host,
            'port': port,
            'id': uuid,
        }
        
        if params:
            params_dict = parse_qs(params[1:])
            config.update({
                'type': params_dict.get('type', ['tcp'])[0],
                'security': params_dict.get('security', ['none'])[0],
                'sni': params_dict.get('sni', [host])[0],
                'encryption': params_dict.get('encryption', ['none'])[0],
            })
        
        return {
            'id': f'vless_{hash(url) % 1000000}',
            'name': name,
            'country': location['country'],
            'countryCode': location['countryCode'],
            'protocol': 'vless',
            'configUrl': url,
            'config': config,
            'provider': provider,
            'isPremium': is_premium,
            'tags': ['hunter', 'vless'],
        }
    except:
        return None


def parse_shadowsocks(url: str) -> Optional[Dict]:
    """解析Shadowsocks节点"""
    try:
        # ss://base64(method:password)@host:port#name
        match = re.match(r'ss://([^@#]+)@?([^:#]*):?(\d*)#?(.*)', url)
        if not match:
            return None
        
        encoded, host, port, name = match.groups()
        
        # 解码配置
        try:
            decoded = base64.b64decode(encoded).decode('utf-8')
            method, password = decoded.split(':', 1)
        except:
            method = 'aes-256-gcm'
            password = encoded
        
        name = unquote(name) if name else f'SS-{host}'
        
        # 推测地理位置
        location = guess_location(name + ' ' + host)
        
        # 只保留目标地区的节点
        if location['countryCode'] not in TARGET_REGIONS:
            return None
        
        # 检测提供商
        provider = detect_provider(host)
        is_premium = provider is not None
        
        return {
            'id': f'ss_{hash(url) % 1000000}',
            'name': name,
            'country': location['country'],
            'countryCode': location['countryCode'],
            'protocol': 'shadowsocks',
            'configUrl': url,
            'config': {
                'server': host,
                'server_port': port or '8388',
                'method': method,
                'password': password,
            },
            'provider': provider,
            'isPremium': is_premium,
            'tags': ['hunter', 'shadowsocks'],
        }
    except:
        return None


def parse_node(url: str) -> Optional[Dict]:
    """解析节点URL"""
    if url.startswith('vmess://'):
        return parse_vmess(url)
    elif url.startswith('trojan://'):
        return parse_trojan(url)
    elif url.startswith('vless://'):
        return parse_vless(url)
    elif url.startswith('ss://'):
        return parse_shadowsocks(url)
    return None


async def check_node_quality(node_data: Dict) -> Optional[Dict]:
    """检查节点质量（静默模式）"""
    try:
        config = node_data['config']
        host = config.get('add', config.get('host', config.get('server', '')))
        port = int(config.get('port', config.get('server_port', 443)))
        
        if not host:
            return None
        
        # 清理主机名
        if "/" in host:
            host = host.split('/')[0]
        
        # 测试连接
        start = asyncio.get_event_loop().time()
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=3.0
            )
            writer.close()
            await writer.wait_closed()
        except:
            return None
        
        latency = int((asyncio.get_event_loop().time() - start) * 1000)
        
        # 更新节点数据
        node_data['latency'] = latency
        node_data['isAvailable'] = True
        
        # 计算评分
        score = 0.5
        if node_data['isPremium']:
            score += 0.2
        if latency < 100:
            score += 0.2
        elif latency < 200:
            score += 0.1
        if node_data['countryCode'] in TARGET_REGIONS:
            score += 0.1
        
        node_data['score'] = min(score, 1.0)
        
        return node_data
    except:
        return None


async def main():
    """主函数（静默模式）"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
        all_content = ""
        
        # 获取所有源的内容（静默）
        for url in HUNTER_SOURCES:
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    text = r.text
                    # 尝试Base64解码
                    for _ in range(2):
                        if "://" not in text[:50]:
                            try:
                                text = base64.b64decode(text).decode('utf-8')
                            except:
                                break
                    all_content += text + "\n"
            except:
                continue
        
        # 提取所有节点URL
        node_urls = list(set(re.findall(r'(?:ss|vmess|trojan|vless)://[^\s]+', all_content)))
        
        if not node_urls:
            return
        
        # 解析节点（只保留目标地区）
        parsed_nodes = []
        for url in node_urls:
            node_data = parse_node(url)
            if node_data:
                parsed_nodes.append(node_data)
        
        # 测试节点质量
        tasks = [check_node_quality(node) for node in parsed_nodes]
        results = await asyncio.gather(*tasks)
        
        # 过滤有效节点
        valid_nodes = [r for r in results if r]
        
        # 排序：优质节点优先，然后按延迟排序
        valid_nodes.sort(key=lambda x: (-x['isPremium'], x['latency']))
        
        # 取前50个
        final_nodes = valid_nodes[:50]
        
        # 统计信息
        stats = {
            'total': len(final_nodes),
            'premium': sum(1 for n in final_nodes if n['isPremium']),
            'by_country': {},
            'by_protocol': {},
        }
        
        for node in final_nodes:
            country = node['countryCode']
            protocol = node['protocol']
            stats['by_country'][country] = stats['by_country'].get(country, 0) + 1
            stats['by_protocol'][protocol] = stats['by_protocol'].get(protocol, 0) + 1
        
        # 准备输出数据
        node_data = json.dumps(final_nodes, ensure_ascii=False)
        
        # 加密或编码
        if ENABLE_ENCRYPTION:
            encrypted_data = xor_encrypt(node_data, ENCRYPTION_KEY)
        else:
            encrypted_data = base64.b64encode(node_data.encode()).decode()
        
        # 输出JSON
        output = {
            "data": encrypted_data,
            "timestamp": str(asyncio.get_event_loop().time()),
            "count": len(final_nodes),
            "encrypted": ENABLE_ENCRYPTION,
            "version": "2.0",
            "stats": stats
        }
        
        # 保存文件
        with open('nodes.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    asyncio.run(main())
