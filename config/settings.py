import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # 飞书
    FEISHU_APP_ID: str = os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET: str = os.getenv("FEISHU_APP_SECRET", "")

    # LLM
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")

    FEISHU_VERIFICATION_TOKEN: str = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
    FEISHU_ENCRYPT_KEY: str = os.getenv("FEISHU_ENCRYPT_KEY", "")

    # 飞书多维表格
    BITABLE_APP_TOKEN: str = os.getenv("BITABLE_APP_TOKEN", "")
    BITABLE_TABLE_ID: str = os.getenv("BITABLE_TABLE_ID", "")

    # 飞书审批
    APPROVAL_CODE: str = os.getenv("APPROVAL_CODE", "")


settings = Settings()
