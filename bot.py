# 在文件顶部添加
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('马蹄小莲机器人')

# 替换所有 print 为 logger.info
# 例如：
logger.info(f"开始运行机器人...")
import requests
import os
import re
import time
from datetime import datetime, timedelta, timezone

# 从环境变量获取配置
MASTODON_TOKEN = os.getenv('MASTODON_TOKEN')
INSTANCE_URL = os.getenv('INSTANCE_URL')
DEEPSEEK_KEY = os.getenv('DEEPSEEK_KEY')

def extract_text(html):
    """去除HTML标签，返回纯文本"""
    return re.sub(r'<[^>]+>', '', html) if html else ""

def call_deepseek(prompt):
    """调用DeepSeek API生成回复"""
    if not prompt or len(prompt.strip()) < 2:
        return "有什么我可以帮你的吗？(◕‿◕✿)"
    
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_KEY}",
        "Content-Type": "application/json"
    }
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
            return f"抱歉，我现在有点忙，稍后再聊好吗？(；′⌒`) [错误: {response.status_code}]"
    except Exception as e:
        return f"啊啦，我的小脑袋有点混乱了...请再说一次好吗？(>_<) [错误: {str(e)[:30]}]"

def run_bot():
    """主函数：获取通知并回复"""
    print(f"{datetime.now(timezone.utc).isoformat()} 开始运行机器人...")
    
    try:
        # 设置时间范围（最近15分钟）
        since_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        url = f"{INSTANCE_URL}/api/v1/notifications?types=mention&since={since_time}"
        
        print(f"获取通知URL: {url}")
        
        # 获取通知
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {MASTODON_TOKEN}"},
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"获取通知失败: {response.status_code}")
            return
            
        notifications = response.json()
        print(f"找到 {len(notifications)} 条通知")
        
        for note in notifications:
            # 检查通知格式
            if not note.get('status') or not isinstance(note['status'], dict):
                continue
                
            status = note['status']
            content = extract_text(status.get('content', '')).lower()
            account = status.get('account', {})
            account_name = account.get('acct', '朋友')
            
            print(f"处理来自 @{account_name} 的通知")
            
            # 检查触发词
            if "马蹄莲马蹄莲" in content:
                # 提取用户文本（移除触发词）
                user_text = content.replace("马蹄莲马蹄莲", "").strip()
                if not user_text:
                    user_text = "你今天想聊些什么呢？(｡･ω･｡)"
                
                print(f"用户内容: {user_text[:50]}...")
                
                # 生成回复
                reply_text = call_deepseek(user_text)
                print(f"生成回复: {reply_text[:50]}...")
                
                # 发送回复
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
                else:
                    print(f"回复失败: {resp.status_code}")
                    
        print("机器人运行完成")
        
    except Exception as e:
        print(f"运行出错: {str(e)}")

if __name__ == "__main__":
    run_bot()
