import os
from pydantic import BaseModel

class Settings(BaseModel):
    chroma_persist_dir: str = os.getenv("CHROMA_PERSIST_DIR", "/tmp/chroma_db")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

settings = Settings()
