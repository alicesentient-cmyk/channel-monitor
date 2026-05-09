#!/usr/bin/env python3
"""数据更新脚本 - 将本地抓取数据同步到频道监控仓库"""

import json
import os
import base64
from datetime import datetime, timedelta

# 路径配置 - 使用绝对路径
SOURCE_DIR = '/Users/mybot/channel_data'
DEST_DIR = '/Users/mybot/channel-monitor'
DATA_FILE = os.path.join(DEST_DIR, 'data.json')
INDEX_FILE = os.path.join(DEST_DIR, 'index.html')

def clean_old_messages(messages):
    """清除5天前的消息"""
    cutoff = datetime.now() - timedelta(days=5)
    
    filtered = []
    for m in messages:
        try:
            dt = datetime.fromisoformat(m.get('datetime', '').replace('Z', '+00:00'))
            if dt.replace(tzinfo=None) >= cutoff:
                filtered.append(m)
        except:
            filtered.append(m)  # 保留无法解析时间的消息
    
    removed = len(messages) - len(filtered)
    if removed > 0:
        print(f"🧹 清除 {removed} 条5天前的消息")
    
    return filtered

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
    
    # 清除5天前的消息
    all_messages = clean_old_messages(all_messages)
    
    return all_messages

def update_data():
    """更新数据文件"""
    messages = load_channel_data()
    
    data = {
        'messages': messages,
        'count': len(messages),
        'updated_at': datetime.now().isoformat()
    }
    
    # 强制写入文件
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()  # 强制刷新缓冲区
        os.fsync(f.fileno())  # 强制同步到磁盘
    
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
    
    # 查找 _d 变量的开始和结束位置
    start_marker = 'const _d = "'
    start = html.find(start_marker)
    if start == -1:
        print("❌ 未找到 _d 变量")
        return False
    
    start += len(start_marker)
    end = html.find('"', start)
    if end == -1:
        print("❌ _d 变量格式错误")
        return False
    
    # 替换
    new_html = html[:start] + b64_data + html[end:]
    
    # 强制写入文件
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        f.write(new_html)
        f.flush()  # 强制刷新缓冲区
        os.fsync(f.fileno())  # 强制同步到磁盘
    
    print(f"✅ 已更新 index.html")
    return True

def git_push():
    """推送到GitHub"""
    os.chdir(DEST_DIR)
    os.system('git add .')
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    os.system(f'git commit -m "update: {timestamp}"')
    # 先 pull 再 push，避免冲突
    os.system('git pull --rebase origin main')
    os.system('git push origin main')
    print("✅ 已推送到GitHub")

if __name__ == '__main__':
    data = update_data()
    if update_index(data):
        git_push()
    else:
        print("❌ 更新失败，未推送")