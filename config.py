from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bot_token = os.getenv("BOT_TOKEN")


config = Config()

