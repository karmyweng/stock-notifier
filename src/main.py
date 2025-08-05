import os
import requests
import json
from datetime import datetime, time
import pytz

# 配置参数
WECOM_WEBHOOK = os.environ["WECOM_WEBHOOK"]
KV_API_URL = os.environ["KV_API_URL"]
KV_API_TOKEN = os.environ["KV_API_TOKEN"]
TIMEZONE = pytz.timezone('Asia/Shanghai')

def get_shanghai_stocks():
    """获取上交所新股公告"""
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(
            "http://www.sse.com.cn/disclosure/announcement/listing/", 
            headers=headers, 
            timeout=15
        )
        response.encoding = 'utf-8'
        
        # 解析HTML
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')
        stocks = []
        
        for item in soup.select('.sse_list_1 dl'):
            date_span = item.select_one('dd span')
            if date_span and date_span.text.strip() == today:
                link = item.select_one('dd a')
                if link and '上市' in link.get('title', ''):
                    stocks.append({
                        "title": link.get('title', ''),
                        "url": f"http://www.sse.com.cn{link['href']}",
                        "exchange": "上交所"
                    })
        return stocks
    except Exception as e:
        print(f"上交所爬取失败: {str(e)}")
        return []

def get_shenzhen_stocks():
    """获取深交所新股公告"""
    today = datetime.now(TIMEZONE).strftime("%Y%m%d")
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01"
        })
        
        # 获取初始Cookie
        session.get("http://www.szse.cn/disclosure/listed/notice/", timeout=10)
        
        # 查询公告
        response = session.post(
            "http://www.szse.cn/api/disc/announcement/annList",
            json={
                "seDate": [f"{today}", f"{today}"],
                "channelCode": ["listedNotice_disc"],
                "pageSize": 20,
                "pageNum": 1
            },
            timeout=15
        )
        
        stocks = []
        for item in response.json().get("data", []):
            title = item.get("title", "")
            if "上市" in title and ("创业板" in title or "主板" in title):
                stocks.append({
                    "title": title,
                    "url": f"http://www.szse.cn{item['attachPath']}",
                    "exchange": "深交所"
                })
        return stocks
    except Exception as e:
        print(f"深交所爬取失败: {str(e)}")
        return []

def send_wecom_message(stocks):
    """发送企业微信消息"""
    if not stocks:
        return False, "无新股数据"
    
    markdown_content = "## 📈 今日新股认购提醒\n\n"
    for idx, stock in enumerate(stocks, 1):
        markdown_content += f"{idx}. **{stock['exchange']}** [{stock['title']}]({stock['url']})\n"
    
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": markdown_content
        }
    }
    
    try:
        resp = requests.post(WECOM_WEBHOOK, json=payload, timeout=10)
        result = resp.json()
        if result.get("errcode") == 0:
            return True, "推送成功"
        return False, f"企业微信错误: {result.get('errmsg')}"
    except Exception as e:
        return False, f"推送失败: {str(e)}"

def get_kv_state():
    """从Cloudflare KV获取状态"""
    try:
        resp = requests.get(
            f"{KV_API_URL}/state",
            headers={"Authorization": f"Bearer {KV_API_TOKEN}"},
            timeout=5
        )
        if resp.status_code == 200:
            return resp.json().get("last_sent_date", "")
    except:
        pass
    return ""

def set_kv_state(date):
    """设置Cloudflare KV状态"""
    try:
        requests.put(
            f"{KV_API_URL}/state",
            json={"last_sent_date": date},
            headers={"Authorization": f"Bearer {KV_API_TOKEN}"},
            timeout=5
        )
        return True
    except:
        return False

def is_trading_time():
    """检查是否为交易时段"""
    now = datetime.now(TIMEZONE)
    
    # 周一至周五
    if now.weekday() >= 5:
        return False
    
    current_time = now.time()
    # 上午交易时间 9:30-11:30
    if time(9, 30) <= current_time <= time(11, 30):
        return True
    # 下午交易时间 13:00-15:00
    if time(13, 0) <= current_time <= time(15, 0):
        return True
    
    return False

def main():
    print("="*50)
    print(f"执行时间: {datetime.now(TIMEZONE)}")
    
    # 检查交易时段
    if not is_trading_time():
        print("非交易时段，跳过执行")
        return
    
    # 检查是否已发送
    today_str = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    if get_kv_state() == today_str:
        print("今日已发送，跳过执行")
        return
    
    # 获取新股数据
    print("获取新股数据...")
    stocks = get_shanghai_stocks() + get_shenzhen_stocks()
    
    if not stocks:
        print("无新股数据")
        return
    
    # 发送消息
    success, msg = send_wecom_message(stocks)
    print(f"推送结果: {msg}")
    
    # 成功则记录状态
    if success:
        set_kv_state(today_str)
        print("状态已更新")

if __name__ == "__main__":
    main()
