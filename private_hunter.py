import asyncio, httpx, base64, re, json, os

# 这里加入一些“资源聚合器”的 URL，它们专门收集全网泄露的私人订阅
HUNTER_SOURCES = [
    httpsraw.githubusercontent.comzufuliproxypoolmasterproxypoolresourcessources.txt, # 节点源的源
    httpsraw.githubusercontent.comvpeifreemasterv2ray,
    httpsapi.kkss.pwsubscribecollector=github, # 自动汇总 GitHub 泄露的节点
]

async def check_node_quality(node_url)
    
    不仅测延迟，还要通过域名后缀识别“私人”特征
    例如包含 'edu', 'amazon', 'azure', 'oracle' 的通常是私人高性能服务器
    
    try
        match = re.search(r'@(.)(d+)', node_url)
        if not match return None
        host, port = match.groups()
        
        start = asyncio.get_event_loop().time()
        # 尝试建立握手
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, int(port)), timeout=1.2)
        writer.close()
        latency = (asyncio.get_event_loop().time() - start)  1000
        
        # 权重计算：如果是私人大厂云（如 Oracle, AWS），权重更高
        priority = 1
        if any(cloud in host for cloud in ['aws', 'azure', 'compute', 'oracle', 'google'])
            priority = 2
            
        return {url node_url, latency latency, priority priority}
    except return None

async def main()
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client
        # 1. 执行“捡漏”抓取
        all_content = 
        for url in HUNTER_SOURCES
            try
                r = await client.get(url)
                if r.status_code == 200
                    text = r.text
                    # 尝试解密可能存在的 Base64 订阅
                    if  not in text[30]
                        try text = base64.b64decode(text).decode('utf-8')
                        except pass
                    all_content += text + n
            except continue

        # 2. 正则提取
        nodes = list(set(re.findall(r'(ssvmesstrojanvless)[^s]+', all_content)))
        print(f[] 发现候选节点 {len(nodes)} 个，开始筛选私人优质资源...)

        # 3. 并发扫描
        tasks = [check_node_quality(n) for n in nodes]
        results = await asyncio.gather(tasks)
        
        # 4. 排序逻辑：优先选择延迟低且来自大厂云（私人）的节点
        scored_nodes = [r for r in results if r]
        scored_nodes.sort(key=lambda x (x['priority'] == 1, x['latency'])) # 优先排 priority=2 的
        
        final_list = [n['url'] for n in scored_nodes[40]] # 取前 40 个
        
        # 5. 输出加密 JSON
        encrypted = base64.b64encode(json.dumps(final_list).encode()).decode()
        with open('nodes.json', 'w') as f
            json.dump({data encrypted, timestamp os.environ.get('GITHUB_RUN_ID', 'local')}, f)
        print(f[!] 捡漏成功，已更新优质节点池。)

if __name__ == __main__
    asyncio.run(main())