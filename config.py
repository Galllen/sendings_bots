from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)
@dataclass
class Config:
    bot_token: str = os.getenv("BOT_TOKEN")
    TELEGRAM_API_ID: int = int(os.getenv('TELEGRAM_API_ID', '0'))
    TELEGRAM_API_HASH: str = os.getenv('TELEGRAM_API_HASH', '')
    admin: str = os.getenv('acc_admin')
    SESSIONS_DIR: str = SESSIONS_DIR

config = Config()

