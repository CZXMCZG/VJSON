import asyncio, httpx, base64, re, json, os

# 增强版源列表：混合了订阅源、聚合源和直接节点源
HUNTER_SOURCES = [
    "https://raw.githubusercontent.com/freefq/free/master/v2",
    "https://raw.githubusercontent.com/zufuli/proxypool/master/proxypool/resources/sources.txt",
    "https://raw.githubusercontent.com/vpei/free/master/v2ray",
    "https://api.kkss.pw/subscribe?collector=github",
    "https://raw.githubusercontent.com/Pawdroid/Free-nodes/main/node.txt",
    "https://raw.githubusercontent.com/mfuu/v2ray/master/v2ray"
]

async def check_node_quality(node_url):
    try:
        # 兼容更多协议格式的正则提取
        match = re.search(r'@(.*?):(\d+)', node_url)
        if not match: 
            # 尝试处理不带@的简单格式 (如部分 ss 链接)
            match = re.search(r'://(.*?):(\d+)', node_url)
        
        if not match: return None
        host, port = match.groups()
        
        # 处理可能的 base64 混淆 host
        if "/" in host: host = host.split('/')[-1]

        start = asyncio.get_event_loop().time()
        # 放宽超时到 3 秒，确保初次运行能抓到东西
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, int(port)), timeout=3.0)
        writer.close()
        latency = (asyncio.get_event_loop().time() - start) * 1000
        
        priority = 1
        if any(cloud in host.lower() for cloud in ['aws', 'azure', 'compute', 'oracle', 'google', 'digitalocean', 'linode', 'vultr']):
            priority = 2
            
        return {"url": node_url, "latency": latency, "priority": priority}
    except: 
        return None

async def main():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36'}
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
        print("[*] 正在启动全网捡漏引擎...")
        all_content = ""
        for url in HUNTER_SOURCES:
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    text = r.text
                    # 强力解码：尝试多次 base64 解码，处理嵌套加密
                    for _ in range(2):
                        if "://" not in text[:50]:
                            try: text = base64.b64decode(text).decode('utf-8')
                            except: break
                    all_content += text + "\n"
                    print(f"[+] 成功抓取源: {url[:30]}...")
                else:
                    print(f"[!] 源响应异常 ({r.status_code}): {url[:30]}")
            except Exception as e:
                print(f"[-] 无法访问源 {url[:30]}: {str(e)}")

        # 匹配所有主流协议
        nodes = list(set(re.findall(r'(?:ss|vmess|trojan|vless)://[^\s]+', all_content)))
        print(f"[*] 共收集到 {len(nodes)} 个原始节点。正在进行云端测速...")

        if not nodes:
            print("[!!!] 警告：未发现任何节点字符串，请检查源地址是否有效。")
            return

        # 并发检测
        tasks = [check_node_quality(n) for n in nodes]
        results = await asyncio.gather(*tasks)
        
        scored_nodes = [r for r in results if r]
        # 排序：高优先级在前，同级延迟低在前
        scored_nodes.sort(key=lambda x: (-x['priority'], x['latency']))
        
        # 即使没捡到“私人”的，也保底取前 50 个能通的
        final_list = [n['url'] for n in scored_nodes[:50]]
        
        # 加密输出
        encrypted = base64.b64encode(json.dumps(final_list).encode()).decode()
        with open('nodes.json', 'w') as f:
            json.dump({"data": encrypted, "timestamp": str(asyncio.get_event_loop().time()), "count": len(final_list)}, f)
        
        print(f"[!] 任务完成。成功筛选出 {len(final_list)} 个可用节点。")

if __name__ == "__main__":
    asyncio.run(main())