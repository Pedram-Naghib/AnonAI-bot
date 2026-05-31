import base64
# ToDo save in a database
def encode_user_id(user_id: int) -> str:
    """تبدیل آیدی عددی به یک رشته متنی امن برای لینک ناشناس"""
    # تبدیل عدد به بایت
    id_bytes = str(user_id).encode('utf-8')
    # انکود کردن به base64
    b64_bytes = base64.urlsafe_b64encode(id_bytes)
    # تبدیل به استرینگ و حذف علامت‌های مساوی (=) برای شیک شدن لینک
    return b64_bytes.decode('utf-8').rstrip('=')

def decode_user_id(encoded_str: str) -> int:
    """تبدیل مجدد رشته متنی لینک به آیدی عددی اصلی"""
    try:
        # اضافه کردن مساوی‌های حذف شده برای استاندارد شدن b64
        padding = '=' * (4 - len(encoded_str) % 4)
        full_encoded_str = encoded_str + padding
        
        # دکود کردن
        id_bytes = base64.urlsafe_b64decode(full_encoded_str.encode('utf-8'))
        return int(id_bytes.decode('utf-8'))
    except Exception:
        # اگر کسی لینک رو دستکاری کرده باشه، مقدار None برمی‌گردونه
        return None