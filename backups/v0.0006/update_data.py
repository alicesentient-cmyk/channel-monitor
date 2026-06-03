#!/usr/bin/env python3
"""数据更新脚本 - 将本地抓取数据同步到频道监控仓库 (v0.0006 - AI标题生成)"""

import json
import os
import base64
import re
import time
from datetime import datetime, timedelta

# 路径配置 - 全部硬编码绝对路径，彻底避免 expanduser 路径陷阱
SOURCE_DIR = '/Users/mybot/channel_data'
DEST_DIR = '/Users/mybot/channel-monitor'
DATA_FILE = os.path.join(DEST_DIR, 'data.json')
INDEX_FILE = os.path.join(DEST_DIR, 'index.html')
CACHE_FILE = os.path.join(DEST_DIR, 'title_cache.json')

# DeepSeek API 配置
DEEPSEEK_BASE_URL = 'https://api.deepseek.com/v1/chat/completions'
DEEPSEEK_MODEL = 'deepseek-chat'

def get_deepseek_api_key():
    """从配置文件读取 DeepSeek API Key"""
    config_path = '/Users/mybot/.hermes/config.yaml'
    try:
        with open(config_path, 'r') as f:
            content = f.read()
        
        # 从 custom_providers 部分查找 Api.deepseek.com 的 key
        import re
        match = re.search(r'Api\.deepseek\.com.*?api_key:\s*(sk-[a-zA-Z0-9]+)', content, re.DOTALL)
        if match:
            return match.group(1)
        
        # 从 providers 部分查找 deepseek 的 key
        match = re.search(r'deepseek:\s*\n.*?api_key:\s*(sk-[a-zA-Z0-9]+)', content, re.DOTALL)
        if match:
            return match.group(1)
    except Exception as e:
        print(f"⚠️ 读取配置文件失败: {e}")
    
    return os.environ.get('DEEPSEEK_API_KEY', '')

def load_title_cache():
    """加载标题缓存，避免重复调用API"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

def save_title_cache(cache):
    """保存标题缓存"""
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def generate_titles_with_ai(text):
    """调用 DeepSeek API 生成标题"""
    import urllib.request
    import urllib.error
    
    api_key = get_deepseek_api_key()
    if not api_key:
        print("⚠️ 未找到 DeepSeek API Key，跳过AI标题生成")
        return None
    
    # 截取前300字符作为上下文
    context = text[:300]
    
    prompt = f"""你是标题生成专家。请为以下新闻生成3个标题候选。

要求：
1. 每个标题 ≤ 20 字符（含标点），这是硬性约束，超过会导致系统崩溃
2. 去除所有修饰词，保留核心主谓宾或最关键的数据/事实
3. 三种视角：
   - conclusion: 结论型（直接概括核心事实）
   - attractive: 吸引型（突出信息增量或痛点）
   - minimal: 极简型（仅用核心关键词组合）

原文：{context}

请直接返回JSON格式，不要有任何其他文字：
{{"conclusion": "标题内容", "attractive": "标题内容", "minimal": "标题内容", "best": "conclusion"}}"""

    try:
        data = json.dumps({
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": "你是标题生成专家，只返回JSON格式结果。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 200
        }).encode('utf-8')
        
        req = urllib.request.Request(
            DEEPSEEK_BASE_URL,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
        )
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            content = result['choices'][0]['message']['content']
            
            # 提取JSON部分
            json_match = re.search(r'\{[^}]+\}', content)
            if json_match:
                titles = json.loads(json_match.group())
                # 验证长度
                for key in ['conclusion', 'attractive', 'minimal']:
                    if key in titles and len(titles[key]) > 20:
                        # 截断到20字符
                        titles[key] = titles[key][:19] + '…'
                return titles
                
    except Exception as e:
        print(f"⚠️ AI标题生成失败: {e}")
    
    return None

def generate_fallback_title(text):
    """生成备用标题（规则引擎，无AI）"""
    # 去除emoji和频道信息
    clean = strip_emoji(text)
    clean = strip_channel_info(clean)
    
    # 提取核心信息
    # 尝试找第一个句号前的内容
    first_sentence = re.split(r'[。！？\n]', clean)[0]
    
    # 如果太长，截取关键部分
    if len(first_sentence) > 20:
        # 尝试找主谓宾结构
        # 去除"的"后面的部分
        parts = re.split(r'的', first_sentence)
        if len(parts) > 1:
            title = parts[0]
        else:
            title = first_sentence[:19] + '…'
    else:
        title = first_sentence
    
    return title

def strip_emoji(text):
    """去除文本中的 emoji 符号"""
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
    
    if len(text.strip()) < 20:
        return False
        
    return True

def clean_old_messages(messages):
    """清除36小时前的消息"""
    cutoff = datetime.now() - timedelta(hours=36)
    
    filtered = []
    for m in messages:
        try:
            dt = datetime.fromisoformat(m.get('datetime', '').replace('Z', '+00:00'))
            if dt.replace(tzinfo=None) >= cutoff:
                filtered.append(m)
        except:
            filtered.append(m)
    
    removed = len(messages) - len(filtered)
    if removed > 0:
        print(f"🧹 清除 {removed} 条36小时前的消息")
    
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
        
        if not is_news_content(text):
            filtered_count += 1
            continue
        
        clean_text = strip_emoji(text)
        clean_text = strip_channel_info(clean_text)
        
        m['text'] = clean_text
        if 'title' in m:
            m['title'] = strip_emoji(m['title'])
            m['title'] = strip_channel_info(m['title'])
        
        cleaned.append(m)
    
    if filtered_count > 0:
        print(f"🧹 过滤 {filtered_count} 条非新闻内容")
    
    cleaned.sort(key=lambda x: x.get('datetime') or '', reverse=True)
    cleaned = clean_old_messages(cleaned)
    
    return cleaned

def generate_titles_for_messages(messages):
    """为消息生成AI标题"""
    cache = load_title_cache()
    updated = 0
    api_calls = 0
    
    for m in messages:
        msg_id = m.get('id', '')
        text = m.get('text', '')
        
        # 如果已有缓存的AI标题，直接使用
        if msg_id in cache and 'ai_title' in cache[msg_id]:
            m['title'] = cache[msg_id]['ai_title']
            m['title_options'] = cache[msg_id].get('title_options', {})
            continue
        
        # 生成AI标题
        titles = generate_titles_with_ai(text)
        api_calls += 1
        
        if titles:
            # 使用AI选择的最佳标题
            best_key = titles.get('best', 'conclusion')
            best_title = titles.get(best_key, titles.get('conclusion', ''))
            
            # 确保不超过20字符
            if len(best_title) > 20:
                best_title = best_title[:19] + '…'
            
            m['title'] = best_title
            m['title_options'] = titles
            
            # 缓存结果
            cache[msg_id] = {
                'ai_title': best_title,
                'title_options': titles,
                'generated_at': datetime.now().isoformat()
            }
            updated += 1
        else:
            # 使用规则引擎生成备用标题
            fallback = generate_fallback_title(text)
            m['title'] = fallback
            cache[msg_id] = {
                'ai_title': fallback,
                'title_options': {'conclusion': fallback, 'attractive': fallback, 'minimal': fallback, 'best': 'conclusion'},
                'generated_at': datetime.now().isoformat(),
                'fallback': True
            }
            updated += 1
        
        # API限流：每秒最多5次调用
        if api_calls % 5 == 0:
            time.sleep(1)
    
    # 保存缓存
    save_title_cache(cache)
    
    if updated > 0:
        print(f"🤖 生成 {updated} 条AI标题 (API调用: {api_calls}次)")
    
    return messages

def update_data():
    """更新数据文件"""
    messages = load_channel_data()
    
    # 生成AI标题
    messages = generate_titles_for_messages(messages)
    
    data = {
        'messages': messages,
        'count': len(messages),
        'updated_at': datetime.now().isoformat()
    }
    
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    
    print(f"✅ 已更新 {len(messages)} 条消息到 data.json")
    return data

def update_index(data):
    """更新 index.html 中的数据"""
    json_str = json.dumps(data, ensure_ascii=False)
    b64_data = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
    
    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        html = f.read()
    
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
    
    new_html = html[:start] + b64_data + html[end:]
    
    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        f.write(new_html)
        f.flush()
        os.fsync(f.fileno())
    
    print(f"✅ 已更新 index.html")
    return True

def git_push():
    """推送到GitHub"""
    os.chdir(DEST_DIR)
    os.system('git add data.json index.html title_cache.json')
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    os.system(f'git commit -m "update: {timestamp}"')
    os.system('git stash')
    os.system('git pull origin main')
    os.system('git stash pop 2>/dev/null || true')
    os.system('git push origin main')
    print("✅ 已推送到GitHub")

if __name__ == '__main__':
    data = update_data()
    if update_index(data):
        git_push()
    else:
        print("❌ 更新失败，未推送")
