# src/update_vectorstore.py
"""JSONLデータからChromaベクトルDBを構築・更新するスクリプト"""

import shutil
import json
from pathlib import Path
from typing import Iterable, List, Dict, Any

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

# ===== パス設定 =====
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "diet_speeches.jsonl"
ACTIVE_DB_DIR = BASE_DIR / "chroma_db"
TEMP_DB_DIR = BASE_DIR / "chroma_db_temp"

# ===== モデル・処理設定 =====
EMBED_MODEL = "intfloat/multilingual-e5-small"
COLLECTION_NAME = "kokkai_diet_all"
MAX_LEN_NO_SPLIT = 1200
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
BATCH_SIZE = 200

# ===== テキストスプリッター =====
splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", "。", "、", " "],
)


def iter_speech_records(jsonl_path: Path) -> Iterable[Dict[str, Any]]:
    """JSONLファイルからレコードを1件ずつ読み込む（ジェネレータ）"""
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def build_base_text(rec: Dict[str, Any]) -> str:
    """レコードからテキストを生成"""
    header = (
        f"【日付】{rec.get('date', '')}\n"
        f"【院】{rec.get('nameOfHouse', '')}\n"
        f"【会議】{rec.get('nameOfMeeting', '')}\n"
        f"【発言者】{rec.get('speaker', '')}\n\n"
    )
    return header + rec.get("speech", "")


def build_metadata(rec: Dict[str, Any], rec_idx: int) -> Dict[str, Any]:
    """レコードからメタデータを生成"""
    return {
        "speechID": rec.get("speechID"),
        "issueID": rec.get("issueID"),
        "date": rec.get("date"),
        "nameOfHouse": rec.get("nameOfHouse"),
        "nameOfMeeting": rec.get("nameOfMeeting"),
        "speaker": rec.get("speaker"),
        "speakerGroup": rec.get("speakerGroup"),
        "speechURL": rec.get("speechURL"),
        "meetingURL": rec.get("meetingURL"),
        "record_index": rec_idx,
    }


def build_documents(jsonl_path: Path) -> Iterable[Document]:
    """JSONLからDocumentを生成（必要に応じてチャンク分割）"""
    for rec_idx, rec in enumerate(iter_speech_records(jsonl_path), start=1):
        base_text = build_base_text(rec)
        meta_base = build_metadata(rec, rec_idx)

        # 短いテキストはそのまま1ドキュメント
        if len(base_text) <= MAX_LEN_NO_SPLIT:
            yield Document(
                page_content=base_text,
                metadata={**meta_base, "chunk_index": 0, "chunk_count": 1},
            )
            continue

        # 長いテキストはチャンク分割
        chunks = splitter.split_text(base_text)
        total_chunks = len(chunks)

        for chunk_idx, chunk in enumerate(chunks):
            yield Document(
                page_content=chunk,
                metadata={**meta_base, "chunk_index": chunk_idx, "chunk_count": total_chunks},
            )


def build_vectorstore(persist_dir: Path) -> None:
    """ベクトルDBを構築"""
    # 既存のDBを削除
    if persist_dir.exists():
        print(f"[build] Delete the existing working DB: {persist_dir}")
        shutil.rmtree(persist_dir)

    print("[build] Loading embedding model...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)

    print(f"[build] Creating an empty Chroma collection: {persist_dir}")
    vectorstore = Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=str(persist_dir),
        embedding_function=embeddings,
    )

    print("[build] Document → Chroma adding...")
    batch: List[Document] = []
    total = 0

    for doc in build_documents(DATA_PATH):
        batch.append(doc)
        
        if len(batch) >= BATCH_SIZE:
            vectorstore.add_documents(batch)
            total += len(batch)
            print(f"\r[build] Added: {total} docs", end="", flush=True)
            batch = []

    # 残りのバッチを処理
    if batch:
        vectorstore.add_documents(batch)
        total += len(batch)
        print(f"\r[build] Added: {total} docs", end="", flush=True)

    print("\n[build] Vector DB construction completed (auto-persisted)")


def swap_active_db(temp_dir: Path, active_dir: Path) -> None:
    """作業用DBを本番用DBに昇格（マウントされたディレクトリ対応）"""
    print(f"[swap] Promoting working DB to production DB: {temp_dir} -> {active_dir}")
    
    # active_dir の中身だけを削除（ディレクトリ自体は残す）
    if active_dir.exists():
        print(f"[swap] Clearing contents of: {active_dir}")
        for item in active_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    else:
        active_dir.mkdir(parents=True, exist_ok=True)
    
    # temp_dir の中身を active_dir に移動
    print(f"[swap] Moving contents from {temp_dir} to {active_dir}")
    for item in temp_dir.iterdir():
        shutil.move(str(item), str(active_dir / item.name))
    
    # 空になった temp_dir を削除
    temp_dir.rmdir()
    
    print("[swap] Swap completed successfully")


def main() -> None:
    """メイン処理：ベクトルDB構築と本番環境への切り替え"""
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"JSONL not found: {DATA_PATH}")

    print(f"[main] JSONL: {DATA_PATH.resolve()}")
    print(f"[main] Active DB: {ACTIVE_DB_DIR.resolve()}")
    print(f"[main] Temporary DB: {TEMP_DB_DIR.resolve()}")

    # 1. 一時DBを構築
    build_vectorstore(TEMP_DB_DIR)

    # 2. 本番DBと入れ替え
    swap_active_db(TEMP_DB_DIR, ACTIVE_DB_DIR)


if __name__ == "__main__":
    main()