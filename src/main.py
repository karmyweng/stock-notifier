import os
import requests
import json
from datetime import datetime, timedelta
import pytz
from bs4 import BeautifulSoup

# 配置参数
WECOM_WEBHOOK = os.environ["WECOM_WEBHOOK"]
KV_API_URL = os.environ["KV_API_URL"]
KV_API_TOKEN = os.environ["KV_API_TOKEN"]
TIMEZONE = pytz.timezone('Asia/Shanghai')

def get_new_stocks():
    """从新浪财经获取今日新股信息"""
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    try:
        url = "http://vip.stock.finance.sina.com.cn/corp/go.php/vRPD_NewStockIssue/page/1.phtml"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = 'gbk'  # 新浪使用GBK编码
        
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', id='NewStockTable')
        
        if not table:
            return []
        
        stocks = []
        for row in table.find_all('tr')[1:]:  # 跳过表头
            cols = row.find_all('td')
            if len(cols) < 10:
                continue
                
            # 提取关键信息
            stock_date = cols[0].get_text().strip()
            stock_code = cols[2].get_text().strip()
            stock_name = cols[3].get_text().strip()
            issue_price = cols[5].get_text().strip()
            purchase_limit = cols[7].get_text().strip()
            
            # 检查是否是今天的新股
            if stock_date == today:
                stocks.append({
                    "code": stock_code,
                    "name": stock_name,
                    "price": issue_price,
                    "limit": purchase_limit,
                    "date": stock_date
                })
        
        return stocks
    except Exception as e:
        print(f"新股数据获取失败: {str(e)}")
        return []

def send_concise_message(stocks):
    """发送简洁版新股信息"""
    if not stocks:
        return False, "无新股数据"
    
    # 创建简洁消息格式
    content = "📈 今日新股认购提醒\n\n"
    for stock in stocks:
        content += (
            f"**{stock['name']} ({stock['code']})**\n"
            f"发行价: {stock['price']}元\n"
            f"申购上限: {stock['limit']}股\n"
            f"申购日期: {stock['date']}\n\n"
        )
    
    # 企业微信消息格式
    payload = {
        "msgtype": "markdown",
        "markdown": {
            "content": content
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
    stocks = get_new_stocks()
    
    if not stocks:
        print("今日无新股数据")
        return
    
    # 发送简洁消息
    success, msg = send_concise_message(stocks)
    print(f"推送结果: {msg}")
    
    # 成功则记录状态
    if success:
        set_kv_state(today_str)
        print("状态已更新")

if __name__ == "__main__":
    main()
