#!/usr/bin/env python3
"""数据更新脚本 - 将本地抓取数据同步到频道监控仓库"""

import json
import os
import re
import base64
from datetime import datetime

# 路径配置
SOURCE_DIR = os.path.expanduser('~/channel_data')
DEST_DIR = os.path.expanduser('~/channel-monitor')
DATA_FILE = os.path.join(DEST_DIR, 'data.json')
INDEX_FILE = os.path.join(DEST_DIR, 'index.html')

def load_channel_data():
    """加载所有频道数据"""
    all_messages = []
    
    for filename in os.listdir(SOURCE_DIR):
        if filename.endswith('.json'):
            filepath = os.path.join(SOURCE_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    messages = data.get('messages', [])
                    all_messages.extend(messages)
            except Exception as e:
                print(f"❌ 加载 {filename} 失败: {e}")
    
    # 按时间排序（新的在前）
    all_messages.sort(key=lambda x: x.get('datetime', ''), reverse=True)
    
    return all_messages

def update_data():
    """更新数据文件"""
    messages = load_channel_data()
    
    data = {
        'messages': messages,
        'count': len(messages),
        'updated_at': datetime.now().isoformat()
    }
    
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 已更新 {len(messages)} 条消息到 data.json")
    return data

def update_index(data):
    """更新 index.html 中的数据"""
    # Base64 编码
    json_str = json.dumps(data, ensure_ascii=False)
    b64_data = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
    
    # 读取 index.html
    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # 替换 _d 变量
    pattern = r'const _d = "[^"]+";'
    replacement = f'const _d = "{b64_data}";'
    new_html = re.sub(pattern, replacement, html)
    
    # 写入
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        f.write(new_html)
    
    print(f"✅ 已更新 index.html")

def git_push():
    """推送到GitHub"""
    os.chdir(DEST_DIR)
    os.system('git add .')
    os.system(f'git commit -m "update: {datetime.now().strftime(\"%Y-%m-%d %H:%M\")}"')
    os.system('git push origin main')
    print("✅ 已推送到GitHub")

if __name__ == '__main__':
    data = update_data()
    update_index(data)
    git_push()
