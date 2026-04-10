import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'clarkson-far-2026-secret-key')
    WTF_CSRF_ENABLED = True