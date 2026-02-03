async def main():
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        print("启动分布式避雷抓取模式...")
        raw_urls = []
        
        for url in HUNTER_SOURCES:
            content = await fetch_with_retry(client, url)
            if not content:
                continue
            
            # --- 逻辑增强：自动识别并处理 Base64 编码的源 ---
            # 很多源会把所有节点打包成一个 Base64 字符串
            effective_content = content
            if not re.search(r'://', content) and len(content) > 32:
                try:
                    # 尝试清理空白符后解码
                    decoded = base64.b64decode(content.strip()).decode('utf-8')
                    effective_content += "\n" + decoded
                except:
                    pass

            # 基础协议提取 - 增加对更多协议和格式的兼容
            # 修改正则，防止某些源在 URL 中包含特殊字符导致断开
            found = re.findall(r'(?:vmess|vless|trojan|ss|ssr|hysteria2|hy2)://[^\s|#|"\']+', effective_content)
            raw_urls.extend(found)
            
            # 子链探测 - 修正正则以匹配更多订阅格式
            subs = re.findall(r'https?://[^\s\'"]+(?:sub|subscribe|link|token=)[^\s\'"]+', effective_content)
            for s in subs[:5]: # 稍微增加探测深度
                # 转换器中转
                conv_url = f"https://api.v1.mk/sub?target=v2ray&url={quote(s)}"
                sub_content = await fetch_with_retry(client, conv_url)
                if sub_content:
                    try:
                        # 转换器返回的基本都是 Base64
                        decoded_sub = base64.b64decode(sub_content).decode('utf-8', errors='ignore')
                        raw_urls.extend(re.findall(r'(?:vmess|vless|trojan|ss|ssr)://[^\s|#|"\']+', decoded_sub))
                    except:
                        # 如果不是 Base64，直接尝试正则
                        raw_urls.extend(re.findall(r'(?:vmess|vless|trojan|ss|ssr)://[^\s|#|"\']+', sub_content))
        
        parsed_nodes = []
        unique_raw = list(set(raw_urls))
        print(f"原始链接去重后共: {len(unique_raw)} 条，开始解析有效性...")

        for u in unique_raw:
            node = None
            if u.startswith('vmess://'):
                node = parse_vmess(u)
            else:
                # 增强型通用解析
                try:
                    # 提取协议头
                    proto = u.split('://')[0]
                    # 处理名称 ps
                    ps = unquote(u.split('#')[-1]) if '#' in u else "Unnamed"
                    # 提取主机地址
                    host = ""
                    if '@' in u:
                        host_part = u.split('@')[1].split(':')[0].split('/')[0]
                        host = host_part
                    
                    region = get_region_code(ps, host)
                    if region:
                        node = {
                            'id': f'node_{hash(u) % 1000000}',
                            'name': ps,
                            'country': region,
                            'countryCode': region,
                            'protocol': proto,
                            'configUrl': u,
                            'config': {'add': host, 'port': '443'}
                        }
                except:
                    continue
            
            if node:
                parsed_nodes.append(node)
        
        print(f"安全获取到有效节点: {len(parsed_nodes)} 个")
        
        # 导出 nodes.json (这部分保持原样)
        output = {
            "data": xor_encrypt(json.dumps(parsed_nodes, ensure_ascii=False), ENCRYPTION_KEY) if ENABLE_ENCRYPTION else base64.b64encode(json.dumps(parsed_nodes, ensure_ascii=False).encode()).decode(),
            "count": len(parsed_nodes),
            "timestamp": str(time.time()),
            "encrypted": ENABLE_ENCRYPTION,
            "version": "2.0"
        }
        
        with open('nodes.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        
        print(f"✅ 已导出到 nodes.json")