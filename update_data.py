#!/usr/bin/env python3
"""数据更新脚本 - 将本地抓取数据同步到频道监控仓库"""

import json
import os
from datetime import datetime

# 路径配置
SOURCE_DIR = os.path.expanduser('~/channel_data')
DEST_DIR = os.path.expanduser('~/channel-monitor')
DATA_FILE = os.path.join(DEST_DIR, 'data.json')

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
    
    print(f"✅ 已更新 {len(messages)} 条消息")
    return data

def git_push():
    """推送到GitHub"""
    os.chdir(DEST_DIR)
    os.system('git add .')
    os.system(f'git commit -m "update: {datetime.now().strftime("%Y-%m-%d %H:%M")}"')
    os.system('git push origin main')
    print("✅ 已推送到GitHub")

if __name__ == '__main__':
    update_data()
    git_push()