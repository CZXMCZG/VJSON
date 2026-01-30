import asyncio, httpx, base64, re, json, os

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

def xor_encrypt(data, key):
    data_bytes = data.encode('utf-8')
    key_bytes = key.encode('utf-8')
    result = bytearray()
    
    for i in range(len(data_bytes)):
        result.append(data_bytes[i] ^ key_bytes[i % len(key_bytes)])
    
    return base64.b64encode(result).decode('utf-8')

async def check_node_quality(node_url):
    try:
        match = re.search(r'@(.*?):(\d+)', node_url)
        if not match:
            match = re.search(r'://(.*?):(\d+)', node_url)
        if not match: 
            return None
        
        host, port = match.groups()
        if "/" in host: 
            host = host.split('/')[-1]
        
        start = asyncio.get_event_loop().time()
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, int(port)), 
            timeout=3.0
        )
        writer.close()
        latency = (asyncio.get_event_loop().time() - start) * 1000
        
        priority = 1
        if any(cloud in host.lower() for cloud in [
            'aws', 'azure', 'compute', 'oracle', 'google', 
            'digitalocean', 'linode', 'vultr'
        ]):
            priority = 2
            
        return {"url": node_url, "latency": latency, "priority": priority}
    except: 
        return None

async def main():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'
    }
    
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
        all_content = ""
        
        for url in HUNTER_SOURCES:
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    text = r.text
                    for _ in range(2):
                        if "://" not in text[:50]:
                            try: 
                                text = base64.b64decode(text).decode('utf-8')
                            except: 
                                break
                    all_content += text + "\n"
            except:
                continue

        nodes = list(set(re.findall(r'(?:ss|vmess|trojan|vless)://[^\s]+', all_content)))
        
        if not nodes:
            return

        tasks = [check_node_quality(n) for n in nodes]
        results = await asyncio.gather(*tasks)
        scored_nodes = [r for r in results if r]

        scored_nodes.sort(key=lambda x: (-x['priority'], x['latency']))
        final_list = [n['url'] for n in scored_nodes[:50]]
        
        node_data = json.dumps(final_list)
        
        if ENABLE_ENCRYPTION:
            encrypted_data = xor_encrypt(node_data, ENCRYPTION_KEY)
        else:
            encrypted_data = base64.b64encode(node_data.encode()).decode()
        
        output = {
            "data": encrypted_data,
            "timestamp": str(asyncio.get_event_loop().time()),
            "count": len(final_list),
            "encrypted": ENABLE_ENCRYPTION,
            "version": "2.0"
        }
        
        with open('nodes.json', 'w') as f:
            json.dump(output, f, indent=2)

if __name__ == "__main__":
    asyncio.run(main())