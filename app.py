import os
import requests
import xml.etree.ElementTree as ET
from flask import Flask, jsonify, request
from dotenv import load_dotenv

# Tải biến môi trường từ file .env (nếu đang chạy local)
load_dotenv()

app = Flask(__name__)

# Cấu hình từ biến môi trường
INITIAL_THRESHOLD = float(os.environ.get("INITIAL_THRESHOLD", 28000))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

# Biến global lưu trữ threshold hiện tại trên RAM
current_threshold = INITIAL_THRESHOLD

def send_telegram_message(message, target_chat_id=None):
    """Hàm gửi tin nhắn qua Telegram Bot"""
    if not BOT_TOKEN:
        print("Chưa cấu hình BOT_TOKEN.")
        return False
        
    # Nếu không truyền chat_id mục tiêu, lấy CHAT_ID mặc định từ biến môi trường
    cid = target_chat_id if target_chat_id else CHAT_ID
    if not cid:
        print("Chưa có CHAT_ID.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": cid,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Lỗi khi gửi tin nhắn Telegram: {e}")
        return False

def get_current_euro_rate():
    """Hàm độc lập để gọi API Vietcombank và lấy tỉ giá EUR"""
    url = "https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    
    root = ET.fromstring(response.content)
    for exrate in root.findall('Exrate'):
        if exrate.get('CurrencyCode') == 'EUR':
            buy_str = exrate.get('Buy').replace(',', '')
            return float(buy_str)
    return None

@app.route('/webhook', methods=['POST'])
def webhook():
    """
    Endpoint nhận tin nhắn từ Telegram.
    Khi bạn chat với bot, Telegram sẽ gửi dữ liệu dạng POST về đây.
    """
    global current_threshold
    
    update = request.get_json()
    if not update or "message" not in update or "text" not in update["message"]:
        return jsonify({"status": "ignored"}), 200
        
    chat_id = update["message"]["chat"]["id"]
    text = update["message"]["text"].strip()
    
    if text.startswith("/check"):
        try:
            rate = get_current_euro_rate()
            if rate:
                msg = f"💶 <b>Tỉ giá EUR hiện tại</b>\nGiá mua: <b>{rate:,.0f} VND</b>\n🎯 Ngưỡng đang xét: {current_threshold:,.0f} VND"
            else:
                msg = "❌ Không lấy được tỉ giá EUR lúc này."
            send_telegram_message(msg, chat_id)
        except Exception as e:
            send_telegram_message(f"❌ Lỗi: {str(e)}", chat_id)
            
    elif text.startswith("/threshold"):
        parts = text.split()
        if len(parts) == 2:
            try:
                new_thresh = float(parts[1])
                current_threshold = new_thresh
                send_telegram_message(f"✅ <b>Thành công</b>\nNgưỡng mới đã được đặt thành: <b>{current_threshold:,.0f} VND</b>", chat_id)
            except ValueError:
                send_telegram_message("❌ Sai định dạng. Hãy gõ ví dụ: /threshold 27500", chat_id)
        else:
            send_telegram_message("❌ Thiếu giá trị. Hãy gõ ví dụ: /threshold 27500", chat_id)
            
    elif text.startswith("/help") or text.startswith("/start"):
        help_msg = (
            "🤖 <b>Bot Theo Dõi Tỉ Giá Euro - Hướng Dẫn</b>\n\n"
            "Các lệnh có sẵn:\n"
            "🔹 /check : Xem tỉ giá hiện tại\n"
            "🔹 /threshold &lt;số&gt; : Thay đổi ngưỡng cảnh báo (vd: /threshold 27000)\n"
            "🔹 /help : Xem lại tin nhắn này\n\n"
            "Bot cũng sẽ tự động thông báo cho bạn mỗi 30 phút nếu tỉ giá giảm qua ngưỡng."
        )
        send_telegram_message(help_msg, chat_id)
        
    return jsonify({"status": "ok"}), 200

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({"status": "alive", "current_threshold": current_threshold}), 200

@app.route('/check-rate', methods=['GET'])
def check_rate():
    global current_threshold
    try:
        buy_rate = get_current_euro_rate()
        if buy_rate is None:
            return jsonify({"status": "error", "message": "Không tìm thấy tỉ giá EUR"}), 500
            
        print(f"Đã check giá. Giá mua: {buy_rate}. Ngưỡng: {current_threshold}")
        
        if buy_rate < current_threshold:
            message = (
                f"🚨 <b>THÔNG BÁO TỈ GIÁ EUR MỚI</b>\n"
                f"Tỉ giá mua vào đã giảm!\n\n"
                f"📉 Giá hiện tại: <b>{buy_rate:,.0f} VND</b>\n"
                f"🎯 Ngưỡng cũ: {current_threshold:,.0f} VND\n\n"
                f"🔄 Đã tự động cập nhật ngưỡng mới thành {buy_rate:,.0f} VND."
            )
            
            if send_telegram_message(message):
                current_threshold = buy_rate
                return jsonify({"status": "alert_sent", "new_threshold": current_threshold, "buy_rate": buy_rate}), 200
            else:
                return jsonify({"status": "alert_failed", "message": "Không thể gửi Telegram"}), 500
                
        return jsonify({"status": "checked_no_alert", "buy_rate": buy_rate, "threshold": current_threshold}), 200

    except Exception as e:
        error_msg = f"Lỗi trong quá trình check: {str(e)}"
        print(error_msg)
        return jsonify({"status": "error", "message": error_msg}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
