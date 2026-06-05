import base64
from cryptography.fernet import Fernet

# ==========================================
# 🔏 تنظیمات هسته رمزنگاری (AES-256 Fernet Key)
# ==========================================
# 🎯 فیکس قطعی ارور ValueError: این کلید دقیقاً ۴۴ کاراکتر (۳۲ بایت انکود شده استاندارد) طول دارد.
# از این کلید برای رمزنگاری امن بخش رفرال (ref_) ربات استفاده می‌شود.
_FERNET_KEY = b"n8bA-Z2kM1W9yX4vC7qP0sL3mK5jH2gF1dS4aA7pP0o=" 
_CIPHER = Fernet(_FERNET_KEY)


# ==========================================
# ⛓️ توابع اصلی انکود و دیکود آیدی‌های بخش رفرال
# ==========================================
def encode_user_id(user_id: int) -> str:
    """
    🔏 تبدیل آیدی عددی به رشته متنی رمزنگاری شده برای بخش رفرال (ref_)
    """
    try:
        # تبدیل عدد به بایت
        id_bytes = str(user_id).encode('utf-8')
        
        # رمزنگاری فوق امن با پروتکل Fernet
        encrypted_bytes = _CIPHER.encrypt(id_bytes)
        
        # تبدیل به استرینگ و حذف علامت‌های مساوی (=) برای شیک شدن لینک دعوت تلگرام
        return base64.urlsafe_b64encode(encrypted_bytes).decode('utf-8').rstrip('=')
    except Exception as e:
        print(f"💥 Error encrypting referrer id: {e}")
        return ""


def decode_user_id(encoded_str: str) -> int:
    """
    🔓 رمزگشایی رشته متنی و استخراج آیدی عددی اصلی معرف
    """
    try:
        # بررسی لایه پدینگ برای استانداردسازی مجدد رشته b64
        rem = len(encoded_str) % 4
        if rem > 0:
            encoded_str += '=' * (4 - rem)
            
        # دکود کردن اولیه رشته متنی به بایت‌های رمزنگاری شده
        encrypted_bytes = base64.urlsafe_b64decode(encoded_str.encode('utf-8'))
        
        # رمزگشایی نهایی و اتمیک با کلید اصلی
        decrypted_bytes = _CIPHER.decrypt(encrypted_bytes)
        
        # تبدیل مجدد رشته متنی لینک به آیدی عددی اصلی
        return int(decrypted_bytes.decode('utf-8'))
    except Exception as e:
        # 🛡️ سپر حفاظتی: اگر کسی لینک دعوت را دستکاری کرده باشد، مقدار None برمی‌گرداند
        print(f"🛡️ Security Alert: Invalid referral token decryption attempt: {e}")
        return None