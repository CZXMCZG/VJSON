import asyncio, httpx, base64, re, json, os

# 修正后的源列表，确保每个 URL 都被引号包裹
HUNTER_SOURCES = [
    "https://raw.githubusercontent.com/zufuli/proxypool/master/proxypool/resources/sources.txt",
    "https://raw.githubusercontent.com/vpei/free/master/v2ray",
    "https://api.kkss.pw/subscribe?collector=github", # 这里之前漏掉了引号
]

async def check_node_quality(node_url):
    """
    不仅测延迟，还要通过域名后缀识别“私人”特征
    """
    try:
        # 简单解析提取 IP 和 Port
        match = re.search(r'@(.*?):(\d+)', node_url)
        if not match: return None
        host, port = match.groups()
        
        start = asyncio.get_event_loop().time()
        # 建立真实的 TCP 握手
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, int(port)), timeout=1.2)
        writer.close()
        latency = (asyncio.get_event_loop().time() - start) * 1000
        
        # 识别大厂云（通常代表私人优质服务器）
        priority = 1
        if any(cloud in host.lower() for cloud in ['aws', 'azure', 'compute', 'oracle', 'google', 'digitalocean']):
            priority = 2
            
        return {"url": node_url, "latency": latency, "priority": priority}
    except: return None

async def main():
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers={'User-Agent': 'Mozilla/5.0'}) as client:
        print("[*] 开始扫射全网捡漏...")
        all_content = ""
        for url in HUNTER_SOURCES:
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    text = r.text
                    # 自动处理 Base64 订阅
                    if "://" not in text[:30]:
                        try: text = base64.b64decode(text).decode('utf-8')
                        except: pass
                    all_content += text + "\n"
            except: continue

        # 提取节点协议
        nodes = list(set(re.findall(r'(?:ss|vmess|trojan|vless)://[^\s]+', all_content)))
        print(f"[*] 发现 {len(nodes)} 个原始节点，开始筛选优质资源...")

        # 暴力并发测速
        tasks = [check_node_quality(n) for n in nodes]
        results = await asyncio.gather(*tasks)
        
        # 排序：优先排大厂云(priority=2)，同级按延迟排
        scored_nodes = [r for r in results if r]
        scored_nodes.sort(key=lambda x: (-x['priority'], x['latency']))
        
        final_list = [n['url'] for n in scored_nodes[:50]] # 取前 50 个最强节点
        
        # 输出加密 JSON
        encrypted = base64.b64encode(json.dumps(final_list).encode()).decode()
        with open('nodes.json', 'w') as f:
            json.dump({"data": encrypted, "timestamp": str(asyncio.get_event_loop().time())}, f)
        print(f"[!] 捡漏成功，已更新 {len(final_list)} 个优质节点到 nodes.json。")

if __name__ == "__main__":
    asyncio.run(main())