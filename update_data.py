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

def strip_emoji(text):
    """去除文本中的 emoji 符号"""
    import re
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # 表情符号
        "\U0001F300-\U0001F5FF"  # 符号和象形文字
        "\U0001F680-\U0001F6FF"  # 交通和地图符号
        "\U0001F1E0-\U0001F1FF"  # 旗帜
        "\U0001F900-\U0001F9FF"  # 补充符号
        "\U0001FA00-\U0001FA6F"  # 国际象棋
        "\U0001FA70-\U0001FAFF"  # 符号扩展A
        "\U00002600-\U000026FF"  # 杂项符号
        "\U00002700-\U000027BF"  # 装饰符号
        "\U0000FE00-\U0000FE0F"  # 变体选择符
        "\U0000200D"             # 零宽连接符
        "\U00002300-\U000023FF"  # 技术符号
        "\U00002B50"             # 五角星
        "\U00002B55"             # 圆圈
        "\U00003030"             # 波浪号
        "\U0000303D"             # 等号
        "\U00003297"             # 割
        "\U00003299"             # 秘
        "\U000000A9"             # 版权
        "\U000000AE"             # 注册
        "\U00002122"             # 商标
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub('', text).strip()

def strip_channel_info(text):
    """去除频道信息和无关内容"""
    import re
    # 去除常见的频道标记
    patterns = [
        r'在花频道\s*[·•]\s*茶馆[聊天讨论]*\s*[·•]\s*投稿通道',
        r'在花频道',
        r'茶馆聊天',
        r'茶馆讨论',
        r'投稿通道',
        r'🍵\s*茶馆[聊天讨论]*',
        r'📮\s*投稿通道',
        r'🍀\s*.*?频道',
    ]
    for p in patterns:
        text = re.sub(p, '', text)
    return text.strip()

def is_news_content(text):
    """判断是否为新闻内容，过滤闲聊和互动内容"""
    import re
    # 过滤掉的关键词（闲聊、互动、提醒等）
    noise_patterns = [
        r'宝子们',
        r'记得定.*闹钟',
        r'记得设.*闹钟',
        r'晚安',
        r'早安',
        r'午安',
        r'祝大家',
        r'节日快乐',
        r'新年快乐',
        r'明天见',
        r'后天见',
        r'下周见',
        r'下期见',
        r'下次见',
        r'别忘了',
        r'不要忘记',
        r'提醒一下',
        r'温馨提示',
        r'小提示',
        r'今日份的',
        r'一起加油',
        r'加油鸭',
        r'冲鸭',
    ]
    for p in noise_patterns:
        if re.search(p, text):
            return False
    
    # 太短的内容可能不是新闻
    if len(text.strip()) < 20:
        return False
        
    return True

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
    
    # 清洗数据：去emoji、去频道信息、过滤非新闻
    cleaned = []
    filtered_count = 0
    for m in all_messages:
        text = m.get('text', '')
        
        # 过滤非新闻内容
        if not is_news_content(text):
            filtered_count += 1
            continue
        
        # 清洗文本
        clean_text = strip_emoji(text)
        clean_text = strip_channel_info(clean_text)
        
        # 更新消息数据
        m['text'] = clean_text
        if 'title' in m:
            m['title'] = strip_emoji(m['title'])
            m['title'] = strip_channel_info(m['title'])
        
        cleaned.append(m)
    
    if filtered_count > 0:
        print(f"🧹 过滤 {filtered_count} 条非新闻内容")
    
    # 按时间排序（新的在前）
    cleaned.sort(key=lambda x: x.get('datetime', ''), reverse=True)
    
    # 清除5天前的消息
    cleaned = clean_old_messages(cleaned)
    
    return cleaned

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