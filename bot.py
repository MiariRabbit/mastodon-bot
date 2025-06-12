import requests
import os
import re
import time
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ===== 配置环境变量 =====
MASTODON_TOKEN = os.getenv('MASTODON_TOKEN')
INSTANCE_URL = os.getenv('INSTANCE_URL')
DEEPSEEK_KEY = os.getenv('DEEPSEEK_KEY')

# ===== 基于SQLite的持久化存储 =====
DB_PATH = Path("bot_state.db")

def init_db():
    """初始化数据库并创建表"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 创建状态表
        c.execute('''CREATE TABLE IF NOT EXISTS bot_state (
                     key TEXT PRIMARY KEY, 
                     value TEXT)''')
        
        # 创建消息记录表
        c.execute('''CREATE TABLE IF NOT EXISTS processed_messages (
                     message_hash TEXT PRIMARY KEY,
                     processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # 保存最后运行时间（如果不存在）
        c.execute('''INSERT OR IGNORE INTO bot_state (key, value) 
                     VALUES ('last_run_time', datetime('now'))''')
        
        conn.commit()
        print("数据库初始化完成")
        return True
    except Exception as e:
        print(f"数据库初始化错误: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def get_last_run_time():
    """获取最后运行时间"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT value FROM bot_state WHERE key = 'last_run_time'")
        result = c.fetchone()
        return datetime.fromisoformat(result[0]) if result else datetime.min
    except:
        return datetime.min
    finally:
        if conn:
            conn.close()

def set_last_run_time():
    """更新最后运行时间"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        current_time = datetime.now(timezone.utc).isoformat()
        c.execute("INSERT OR REPLACE INTO bot_state (key, value) VALUES (?, ?)", 
                  ('last_run_time', current_time))
        conn.commit()
    except Exception as e:
        print(f"更新最后运行时间失败: {str(e)}")
    finally:
        if conn:
            conn.close()

def is_message_processed(content):
    """检查消息是否已处理"""
    try:
        # 生成内容哈希值
        message_hash = hashlib.sha256(content.encode()).hexdigest()
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT 1 FROM processed_messages WHERE message_hash = ?", (message_hash,))
        result = c.fetchone()
        
        # 如果未处理，则标记为已处理
        if not result:
            c.execute("INSERT INTO processed_messages (message_hash) VALUES (?)", (message_hash,))
            conn.commit()
            return False
        
        return True
    except Exception as e:
        print(f"消息处理检查失败: {str(e)}")
        return True  # 出错时视为已处理
    finally:
        if conn:
            conn.close()

# ===== 工具函数 =====
def extract_text(html):
    """去除HTML标签，保留纯文本"""
    return re.sub(r'<[^>]+>', '', html) if html else ""

def call_deepseek(prompt):
    """调用 DeepSeek 生成治愈回复"""
    if not prompt or len(prompt.strip()) < 2:
        return "有什么我可以帮你的吗？(◕‿◕✿)"
    
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "deepseek-chat",
        "messages": [
            {
                "role": "system",
                "content": (
                    "你叫马蹄小莲，25岁温柔治愈系姐姐。用生活经验给予心理疏导，"
                    "回复要简短温馨（50字内），结尾添加随机颜文字："
                    "(◕‿◕✿)／(=^･ω･^=)＼(≧▽≦)♪"
                )
            },
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 100,  # 限制回复长度
        "temperature": 0.7
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=8)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"稍后再聊好吗？(；′⌒`)"
    except:
        return "请再说一次好吗？(>_<)"

# ===== 主业务逻辑 =====
def run_bot():
    # 初始化数据库
    if not init_db():
        print("数据库初始化失败，无法继续运行")
        return
    
    current_time = datetime.now(timezone.utc)
    last_run_time = get_last_run_time()
    
    print(f"[{current_time.isoformat()}] 开始运行机器人")
    print(f"上次运行时间: {last_run_time.isoformat()}")
    
    try:
        # 设置时间范围（只处理上次运行后的新消息）
        since_time = last_run_time.isoformat()
        url = f"{INSTANCE_URL}/api/v1/notifications?types=mention&since={since_time}"
        
        print(f"获取通知URL: {url}")
        
        # 获取通知（快速请求）
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {MASTODON_TOKEN}"},
            timeout=5
        )
        
        if response.status_code != 200:
            print(f"获取通知失败: HTTP {response.status_code}")
            return
            
        notifications = response.json()
        print(f"找到 {len(notifications)} 条新通知")
        
        processed_count = 0
        
        for note in notifications:
            # 检查通知格式
            if 'status' not in note or not isinstance(note['status'], dict):
                continue
                
            status = note["status"]
            content_html = status.get('content', '')
            content_text = extract_text(content_html).lower()
            
            # 检查是否已处理（基于内容哈希）
            if is_message_processed(content_html):
                print(f"消息已处理，跳过: {content_text[:30]}...")
                continue
                
            account = status.get('account', {})
            account_name = account.get('acct', '朋友')
            
            print(f"处理来自 @{account_name} 的新通知")
            
            # 检查触发词
            if "马蹄莲马蹄莲" in content_text:
                # 提取用户文本
                user_text = content_text.replace("马蹄莲马蹄莲", "").strip()[:100]
                if not user_text:
                    user_text = "想聊些什么呢？(｡･ω･｡)"
                
                print(f"用户内容: {user_text[:50]}...")
                
                # 生成回复
                reply_text = call_deepseek(user_text)
                print(f"生成回复: {reply_text}")
                
                # 发送回复
                try:
                    resp = requests.post(
                        f"{INSTANCE_URL}/api/v1/statuses",
                        json={
                            "status": f"@{account_name} {reply_text}",
                            "in_reply_to_id": status['id'],
                            "visibility": status.get('visibility', 'public')
                        },
                        headers={"Authorization": f"Bearer {MASTODON_TOKEN}"},
                        timeout=5
                    )
                    
                    if resp.status_code == 200:
                        print(f"成功回复 @{account_name}")
                        processed_count += 1
                    else:
                        print(f"回复失败: HTTP {resp.status_code}")
                except Exception as e:
                    print(f"发送回复时出错: {str(e)}")
            else:
                print("通知不包含触发词，跳过")
        
        # 更新最后运行时间
        set_last_run_time()
        print(f"处理完成，成功回复了 {processed_count} 条通知")
        
    except Exception as e:
        print(f"运行出错: {str(e)}")
    finally:
        # 确保最后运行时间总是更新
        set_last_run_time()

if __name__ == "__main__":
    run_bot()
