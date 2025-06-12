import requests
import os
import re
import time
import hashlib
from datetime import datetime, timedelta, timezone

# ===== 配置环境变量 =====
MASTODON_TOKEN = os.getenv('MASTODON_TOKEN')
INSTANCE_URL = os.getenv('INSTANCE_URL')
DEEPSEEK_KEY = os.getenv('DEEPSEEK_KEY')

# ===== 内存状态存储 =====
processed_ids = set()  # 内存中存储已处理ID
last_run_time = datetime.now(timezone.utc) - timedelta(minutes=5)

# ===== 工具函数 =====
def extract_text(html):
    """去除HTML标签，保留纯文本"""
    return re.sub(r'<[^>]+>', '', html) if html else ""

def generate_notification_id(status):
    """生成唯一通知ID（基于内容哈希）"""
    content = status.get('content', '') + status.get('id', '')
    return hashlib.md5(content.encode()).hexdigest()

def call_deepseek(prompt):
    """调用 DeepSeek 生成治愈回复（优化版）"""
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
    global last_run_time
    
    current_time = datetime.now(timezone.utc)
    print(f"[{current_time.isoformat()}] 开始运行机器人")
    
    try:
        # 设置时间范围（最近1分钟）
        since_time = (current_time - timedelta(minutes=1)).isoformat()
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
            
            # 生成唯一通知ID
            notification_id = generate_notification_id(status)
            
            # 检查是否已处理
            if notification_id in processed_ids:
                print(f"跳过已处理通知: {notification_id}")
                continue
                
            content = extract_text(status.get('content', '')).lower()
            account = status.get('account', {})
            account_name = account.get('acct', '朋友')
            
            print(f"处理来自 @{account_name} 的新通知")
            
            # 检查触发词
            if "马蹄莲马蹄莲" in content:
                # 提取用户文本
                user_text = content.replace("马蹄莲马蹄莲", "").strip()[:100]
                if not user_text:
                    user_text = "想聊些什么呢？(｡･ω･｡)"
                
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
                        # 添加到已处理集合
                        processed_ids.add(notification_id)
                        processed_count += 1
                    else:
                        print(f"回复失败: HTTP {resp.status_code}")
                except Exception as e:
                    print(f"发送回复时出错: {str(e)}")
            else:
                print("通知不包含触发词，跳过")
        
        # 更新最后运行时间
        last_run_time = current_time
        print(f"处理完成，成功回复了 {processed_count} 条通知")
        
    except Exception as e:
        print(f"运行出错: {str(e)}")

if __name__ == "__main__":
    run_bot()
