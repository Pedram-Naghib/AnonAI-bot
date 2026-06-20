from cryptography.fernet import Fernet, InvalidToken
from src.config import FERNET_KEY

if not FERNET_KEY:
    raise ValueError("FERNET_KEY is not set in .env")

_CIPHER = Fernet(FERNET_KEY)


def encode_user_id(user_id: int) -> str:
    """
    Encrypt a numeric user ID into a URL-safe string for referral links.
    Fernet output is already base64 — no need to re-encode.
    """
    try:
        encrypted = _CIPHER.encrypt(str(user_id).encode())
        # Fernet output is URL-safe base64, just strip padding for clean URLs
        return encrypted.decode().rstrip("=")
    except Exception as e:
        print(f"💥 Error encrypting user ID: {e}")
        return ""


def decode_user_id(encoded_str: str) -> int | None:
    """
    Decrypt a referral token back to the original user ID.
    Returns None if the token is invalid or tampered with.
    """
    try:
        # Restore stripped base64 padding
        rem = len(encoded_str) % 4
        if rem:
            encoded_str += "=" * (4 - rem)
        decrypted = _CIPHER.decrypt(encoded_str.encode())
        return int(decrypted.decode())
    except (InvalidToken, ValueError):
        print("🛡️ Security Alert: invalid or tampered referral token")
        return None
    except Exception as e:
        print(f"💥 Error decrypting referral token: {e}")
        return None