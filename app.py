import os
import requests
import xml.etree.ElementTree as ET
from flask import Flask, jsonify
from dotenv import load_dotenv

# Tải biến môi trường từ file .env (nếu đang chạy local)
load_dotenv()

app = Flask(__name__)

# Cấu hình từ biến môi trường
# Khởi tạo threshold với giá trị mặc định là 28000 (như bạn yêu cầu)
INITIAL_THRESHOLD = float(os.environ.get("INITIAL_THRESHOLD", 28000))

# Thông tin bot Telegram
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

# Biến global lưu trữ threshold hiện tại trên RAM
current_threshold = INITIAL_THRESHOLD

def send_telegram_message(message):
    """Hàm gửi tin nhắn qua Telegram Bot"""
    if not BOT_TOKEN or not CHAT_ID:
        print("Chưa cấu hình BOT_TOKEN hoặc CHAT_ID.")
        return False
        
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
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

@app.route('/ping', methods=['GET'])
def ping():
    """
    Endpoint dùng để keep-alive. 
    UptimeRobot/cron-job sẽ gọi vào đây mỗi 10 phút.
    """
    return jsonify({"status": "alive", "current_threshold": current_threshold}), 200

@app.route('/check-rate', methods=['GET'])
def check_rate():
    """
    Endpoint thực hiện quá trình kiểm tra tỉ giá.
    Sẽ được gọi định kỳ (ví dụ mỗi 30 phút).
    """
    global current_threshold
    
    url = "https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx"
    
    try:
        # 1. Gọi API lấy XML từ Vietcombank
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # 2. Phân tích cú pháp XML
        root = ET.fromstring(response.content)
        
        buy_rate = None
        for exrate in root.findall('Exrate'):
            if exrate.get('CurrencyCode') == 'EUR':
                # Giá trị Buy thường có dạng "27,150", cần xóa dấu phẩy để chuyển thành số
                buy_str = exrate.get('Buy').replace(',', '')
                buy_rate = float(buy_str)
                break
                
        if buy_rate is None:
            return jsonify({"status": "error", "message": "Không tìm thấy tỉ giá EUR"}), 500
            
        # 3. So sánh tỉ giá
        result_msg = f"Đã check giá. Giá mua hiện tại: {buy_rate} VND. Ngưỡng: {current_threshold} VND."
        print(result_msg)
        
        if buy_rate < current_threshold:
            # Soạn tin nhắn
            message = (
                f"<b>THÔNG BÁO TỈ GIÁ EUR MỚI</b>\n"
                f"Tỉ giá mua vào đã giảm!\n\n"
                f"- Giá hiện tại: <i><b>{buy_rate:,.0f} VND</b></i>\n"
                f"- Ngưỡng cũ: <i>{current_threshold:,.0f} VND</i>\n\n"
                f"Đã tự động cập nhật ngưỡng mới thành {buy_rate:,.0f} VND."
            )
            
            # Gửi mail/telegram
            if send_telegram_message(message):
                # 4. Cập nhật threshold mới nếu gửi thành công
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
    # Chạy local để test
    app.run(host='0.0.0.0', port=5000)
