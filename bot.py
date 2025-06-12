import requests
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ===== 配置环境变量 =====
MASTODON_TOKEN = os.getenv('MASTODON_TOKEN')
INSTANCE_URL = os.getenv('INSTANCE_URL')
DEEPSEEK_KEY = os.getenv('DEEPSEEK_KEY')

# ===== 创建数据库存储已处理通知 =====
DB_PATH = Path("processed_notifications.db")

def init_db():
    """初始化数据库并清理旧记录"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # 创建表
        c.execute('''CREATE TABLE IF NOT EXISTS processed
                     (id TEXT PRIMARY KEY, created_at TIMESTAMP)''')
        
        # 清理7天前的记录
        cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        c.execute("DELETE FROM processed WHERE created_at < ?", (cutoff,))
        
        conn.commit()
        print(f"数据库初始化完成，清理了 {c.rowcount} 条旧记录")
    except sqlite3.Error as e:
        print(f"数据库初始化错误: {str(e)}")
        # 尝试重建数据库
        if "no such table" in str(e):
            try:
                os.remove(DB_PATH)
                print("重建数据库文件")
                return init_db()  # 递归调用自身
            except:
                print("无法重建数据库文件")
    finally:
        if conn:
            conn.close()

def is_processed(notification_id):
    """检查通知是否已处理"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT id FROM processed WHERE id=?", (notification_id,))
        result = c.fetchone()
        return result is not None
    except sqlite3.Error as e:
        print(f"检查处理状态错误: {str(e)}")
        return False  # 出错时视为未处理
    finally:
        if conn:
            conn.close()

def mark_processed(notification_id):
    """标记通知为已处理"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO processed (id, created_at) VALUES (?, ?)", 
                  (notification_id, datetime.now(timezone.utc).isoformat()))
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"标记已处理错误: {str(e)}")
        return False
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
                    "结尾随机添加日式可爱颜文字，例如：(◕‿◕✿)／(=^･ω･^=)＼(≧▽≦)♪"
                )
            },
            {"role": "user", "content": prompt}
        ]
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=15)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            error_msg = f"DeepSeek API错误: {response.status_code}"
            print(error_msg)
            return f"抱歉，我现在有点忙，稍后再聊好吗？(；′⌒`) [错误: {response.status_code}]"
    except Exception as e:
        error_msg = f"DeepSeek调用异常: {str(e)}"
        print(error_msg)
        return f"啊啦，我的小脑袋有点混乱了...请再说一次好吗？(>_<) [错误: {str(e)[:30]}]"

# ===== 主业务逻辑 =====
def run_bot():
    # 初始化数据库
    init_db()
    
    print(f"[{datetime.now(timezone.utc).isoformat()}] 开始运行机器人")
    
    try:
        # 设置时间范围（最近2分钟）
        since_time = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        url = f"{INSTANCE_URL}/api/v1/notifications?types=mention&since={since_time}"
        
        print(f"获取通知URL: {url}")
        
        # 获取通知
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {MASTODON_TOKEN}"},
            timeout=10
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
                print("无效通知格式，跳过")
                continue
                
            notification_id = note["id"]
            status = note["status"]
            
            # 检查是否已处理
            if is_processed(notification_id):
                print(f"跳过已处理通知: {notification_id}")
                continue
                
            content = extract_text(status.get('content', '')).lower()
            account = status.get('account', {})
            account_name = account.get('acct', '朋友')
            
            print(f"处理来自 @{account_name} 的新通知")
            
            # 检查触发词
            if "马蹄莲马蹄莲" in content:
                # 提取用户文本
                user_text = content.replace("马蹄莲马蹄莲", "").strip()
                if not user_text:
                    user_text = "你今天想聊些什么呢？(｡･ω･｡)"
                
                print(f"用户内容: {user_text[:50]}...")
                
                # 生成回复
                reply_text = call_deepseek(user_text)
                print(f"生成回复: {reply_text[:50]}...")
                
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
                        timeout=10
                    )
                    
                    if resp.status_code == 200:
                        print(f"成功回复 @{account_name}")
                        # 标记为已处理
                        if mark_processed(notification_id):
                            processed_count += 1
                        else:
                            print("标记已处理失败，但回复已发送")
                    else:
                        print(f"回复失败: HTTP {resp.status_code}")
                except Exception as e:
                    print(f"发送回复时出错: {str(e)}")
            else:
                print("通知不包含触发词，跳过")
                
        print(f"处理完成，成功回复了 {processed_count} 条通知")
        
    except Exception as e:
        print(f"运行出错: {str(e)}")

if __name__ == "__main__":
    run_bot()
