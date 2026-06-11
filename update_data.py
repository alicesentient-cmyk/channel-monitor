#!/usr/bin/env python3
"""数据更新脚本 - 将本地抓取数据同步到频道监控仓库 (v0.0010 - Performance优化)"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta

try:
    import yaml as _yaml
except ImportError:
    _yaml = None

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
    """读取 DeepSeek API Key（优先级：环境变量 > YAML解析 > 正则兜底）"""
    # 1. 环境变量优先
    env_key = os.environ.get('DEEPSEEK_API_KEY', '')
    if env_key.startswith('sk-'):
        return env_key

    config_path = '/Users/mybot/.hermes/config.yaml'
    try:
        with open(config_path, 'r') as f:
            content = f.read()
    except IOError as e:
        print(f"⚠️ 读取配置文件失败: {e}")
        return env_key

    # 2. 尝试 YAML 解析（如果安装了 PyYAML）
    if _yaml is not None:
        try:
            cfg = _yaml.safe_load(content)
            # 遍历 custom_providers 找 deepseek
            for provider in (cfg.get('custom_providers') or []):
                if 'deepseek' in str(provider.get('name', '')).lower() or \
                   'deepseek' in str(provider.get('base_url', '')).lower():
                    key = provider.get('api_key', '')
                    if key.startswith('sk-'):
                        return key
            # 遍历 providers 找 deepseek
            providers = cfg.get('providers') or {}
            ds = providers.get('deepseek') or {}
            key = ds.get('api_key', '')
            if key.startswith('sk-'):
                return key
        except Exception as e:
            print(f"⚠️ YAML解析失败，回退到正则: {e}")

    # 3. 正则兜底
    match = re.search(r'deepseek.*?api_key:\s*(sk-[a-zA-Z0-9]+)', content, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1)

    return env_key

def load_title_cache():
    """加载标题缓存，避免重复调用API"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️ 标题缓存读取失败，将重建: {e}")
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
    """去除频道信息、来源归属等无关内容"""
    # 1. 频道品牌信息
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

    # 2. 尾部来源归属："来源via 作者·备用频道·"
    text = re.sub(r'(?:via\s+\S+)?\s*[·•]\s*备用频道\s*[·•]?\s*$', '', text)
    # 3. 尾部来源归属："——来源"（最后一个——到行尾）
    text = re.sub(r'——\s*\S+(?:\s*[、|]\s*\S+)*\s*$', '', text)
    # 4. 尾部 "来源投稿"
    text = re.sub(r'\S+投稿\s*$', '', text)

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
        except (ValueError, TypeError):
            # 无法解析时间的消息保留（宁可多留不可误删）
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

def _generate_one_title(text, api_key):
    """为单条消息生成AI标题（线程安全，不依赖共享状态）"""
    titles = generate_titles_with_ai(text)
    if titles:
        best_key = titles.get('best', 'conclusion')
        best_title = titles.get(best_key, titles.get('conclusion', ''))
        if len(best_title) > 20:
            best_title = best_title[:19] + '…'
        return best_title, titles
    else:
        fallback = generate_fallback_title(text)
        return fallback, {'conclusion': fallback, 'attractive': fallback, 'minimal': fallback, 'best': 'conclusion'}

def generate_titles_for_messages(messages):
    """为消息生成AI标题（并发版，ThreadPoolExecutor + 限流）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    cache = load_title_cache()
    api_key = get_deepseek_api_key()

    # 分离：已缓存 vs 需要生成
    to_generate = []  # (index, msg_id, text)
    for i, m in enumerate(messages):
        msg_id = m.get('id', '')
        if msg_id in cache and 'ai_title' in cache[msg_id]:
            m['title'] = cache[msg_id]['ai_title']
            m['title_options'] = cache[msg_id].get('title_options', {})
        else:
            to_generate.append((i, msg_id, m.get('text', '')))

    if not to_generate:
        return messages

    if not api_key:
        print("⚠️ 未找到 DeepSeek API Key，使用规则引擎生成标题")
        for i, msg_id, text in to_generate:
            fallback = generate_fallback_title(text)
            messages[i]['title'] = fallback
            messages[i]['title_options'] = {'conclusion': fallback, 'attractive': fallback, 'minimal': fallback, 'best': 'conclusion'}
            cache[msg_id] = {'ai_title': fallback, 'title_options': messages[i]['title_options'], 'generated_at': datetime.now().isoformat(), 'fallback': True}
        save_title_cache(cache)
        return messages

    # 限流器：控制API并发速率
    rate_lock = threading.Lock()
    call_times = []

    def rate_limited_generate(idx, msg_id, text):
        with rate_lock:
            now = time.time()
            # 清理1秒前的记录
            while call_times and call_times[0] < now - 1.0:
                call_times.pop(0)
            # 如果1秒内已达3次，等待
            if len(call_times) >= 3:
                wait = 1.0 - (now - call_times[0])
                if wait > 0:
                    time.sleep(wait)
            call_times.append(time.time())

        title, options = _generate_one_title(text, api_key)
        return idx, msg_id, title, options

    # 并发执行
    updated = 0
    api_calls = len(to_generate)
    max_workers = min(3, api_calls)

    print(f"🤖 并发生成 {api_calls} 条AI标题 (workers={max_workers})...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(rate_limited_generate, idx, msg_id, text): (idx, msg_id)
            for idx, msg_id, text in to_generate
        }
        for future in as_completed(futures):
            try:
                idx, msg_id, title, options = future.result()
                messages[idx]['title'] = title
                messages[idx]['title_options'] = options
                cache[msg_id] = {
                    'ai_title': title,
                    'title_options': options,
                    'generated_at': datetime.now().isoformat()
                }
                updated += 1
            except Exception as e:
                idx, msg_id = futures[future]
                fallback = generate_fallback_title(messages[idx].get('text', ''))
                messages[idx]['title'] = fallback
                messages[idx]['title_options'] = {'conclusion': fallback, 'best': 'conclusion'}
                cache[msg_id] = {'ai_title': fallback, 'generated_at': datetime.now().isoformat(), 'fallback': True, 'error': str(e)}
                updated += 1

    save_title_cache(cache)
    print(f"🤖 完成 {updated} 条AI标题 (API调用: {api_calls}次)")
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

def update_index():
    """更新 index.html（不再内嵌数据，仅确保文件存在）"""
    if not os.path.exists(INDEX_FILE):
        print("❌ index.html 不存在")
        return False
    print("✅ index.html 已就绪（数据通过 fetch 加载）")
    return True

def _run_git(args, check=True):
    """执行 git 命令，返回 CompletedResult。失败时打印错误并抛出异常。"""
    result = subprocess.run(
        ['git'] + args,
        cwd=DEST_DIR,
        capture_output=True,
        text=True,
        timeout=60
    )
    if result.returncode != 0:
        print(f"❌ git {' '.join(args)} 失败 (exit {result.returncode})")
        if result.stderr:
            print(f"   stderr: {result.stderr.strip()}")
        if check:
            raise subprocess.CalledProcessError(result.returncode, ['git'] + args, result.stdout, result.stderr)
    return result

def git_push():
    """推送到GitHub（subprocess + 逐步错误处理）"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 1. stage 文件
    _run_git(['add', 'data.json', 'index.html', 'title_cache.json'])

    # 2. commit（允许空提交不报错）
    _run_git(['commit', '-m', f'update: {timestamp}'], check=False)

    # 3. stash → pull → pop（处理远端有新提交的情况）
    _run_git(['stash'], check=False)
    pull_result = _run_git(['pull', 'origin', 'main'], check=False)
    if pull_result.returncode != 0:
        print(f"⚠️ git pull 失败，尝试继续推送: {pull_result.stderr.strip()}")
    _run_git(['stash', 'pop'], check=False)

    # 4. push
    _run_git(['push', 'origin', 'main'])
    print("✅ 已推送到GitHub")

if __name__ == '__main__':
    try:
        data = update_data()
        if update_index():
            git_push()
        else:
            print("❌ 更新失败，未推送")
            sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"❌ Git操作失败: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"❌ 未预期错误: {type(e).__name__}: {e}")
        sys.exit(1)
