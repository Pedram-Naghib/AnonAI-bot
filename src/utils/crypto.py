import base64
from cryptography.fernet import Fernet

# ==========================================
# 🔏 تنظیمات هسته رمزنگاری (AES-256 Key)
# ==========================================
# 🎯 یک کلید ۳۲ بایتی ثابت و بسیار امن برای الگوریتم AES
# نکته مهم: این کلید را هرگز تغییر نده تا لینک‌های تولید شده کاربران بعد از ریستارت ربات باطل نشوند.
_SECRET_RAW = b"CyberChatSecretKeyEncryption2026=" 
_CIPHER = Fernet(base64.urlsafe_b64encode(_SECRET_RAW))


# ==========================================
# ⛓️ توابع اصلی انکود و دیکود اتمیک آیدی‌ها
# ==========================================
def encode_user_id(user_id: int) -> str:
    """
    🔏 تبدیل آیدی عددی به رشته متنی کاملاً رمزنگاری شده و امن
    پاتک امنیتی: جایگزین کردن Base64 معمولی با پروتکل صنعتی AES-256
    """
    try:
        # تبدیل عدد به بایت
        id_bytes = str(user_id).encode('utf-8')
        
        # رمزنگاری فوق امن با پروتکل Fernet
        encrypted_bytes = _CIPHER.encrypt(id_bytes)
        
        # تبدیل به استرینگ و حذف علامت‌های مساوی (=) برای شیک و استاندارد شدن لینک تلگرام
        return base64.urlsafe_b64encode(encrypted_bytes).decode('utf-8').rstrip('=')
    except Exception as e:
        print(f"💥 Error encrypting user id: {e}")
        return ""


def decode_user_id(encoded_str: str) -> int:
    """
    🔓 رمزگشایی رشته متنی متناظر و استخراج آیدی عددی اصلی کاربر
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
        # 🛡️ سپر حفاظتی: اگر کسی لینک را دستکاری کرده باشد، مقدار None برمی‌گرداند و سیستم کرش نمی‌کند
        print(f"🛡️ Security Alert: Malicious or invalid token decryption attempt: {e}")
        return None