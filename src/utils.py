# src/utils.py
"""共通ユーティリティ：パス設定、埋め込みモデル、ヘルパー関数"""

import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document

# ===== パス設定 =====
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PERSIST_DIR = BASE_DIR / "chroma_db"

# ===== モデル設定 =====
COLLECTION_NAME = "kokkai_diet_all"
EMBED_MODEL = "intfloat/multilingual-e5-small"

# ===== 環境変数読み込み =====
load_dotenv(BASE_DIR / ".env")


def get_embeddings() -> HuggingFaceEmbeddings:
    """共通の埋め込みモデルを返す"""
    return HuggingFaceEmbeddings(model_name=EMBED_MODEL)


def format_docs(docs: List[Document]) -> str:
    """Documentリストを1つの文字列に連結"""
    return "\n\n".join(d.page_content for d in docs)