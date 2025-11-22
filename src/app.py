# src/app.py
"""FastAPI による RAG API サーバー"""

from typing import List, Dict, Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.rag_engine import answer_question

# ===== 定数 =====
DEFAULT_TOP_K = 10
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000

# ===== FastAPI アプリ =====
app = FastAPI(
    title="国会発言検索 RAG API",
    description="高市早苗氏の国会発言をベクトル検索するAPI",
    version="1.0.0",
)


# ===== リクエスト/レスポンスモデル =====
class AskRequest(BaseModel):
    """質問リクエスト"""
    question: str = Field(..., description="検索クエリ", example="安全保障について")
    top_k: int = Field(default=DEFAULT_TOP_K, description="検索する文書数", ge=1, le=50)
    session_id: str = Field(default="default", description="セッションID")


class ContextDoc(BaseModel):
    """参照した文書"""
    content: str
    source: str | None


class AskResponse(BaseModel):
    """質問レスポンス"""
    answer: str = Field(..., description="生成された回答")
    context_docs: List[ContextDoc] = Field(..., description="参照した文書リスト")


# ===== エンドポイント =====
@app.get("/health")
def health_check() -> Dict[str, str]:
    """ヘルスチェック"""
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    """
    高市早苗氏の国会発言を検索
    
    例:
```
    curl -X POST http://localhost:8000/ask \\
      -H "Content-Type: application/json" \\
      -d '{"question": "安全保障に関する発言を教えて", "top_k": 3}'
```
    """
    result = answer_question(
        question=req.question,
        top_k=req.top_k,
        session_id=req.session_id,
    )
    
    # context_docs を ContextDoc 形式に変換
    context_docs = [
        ContextDoc(content=doc["content"], source=doc.get("source"))
        for doc in result["context_docs"]
    ]
    
    return AskResponse(
        answer=result["answer"],
        context_docs=context_docs,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.app:app", host=SERVER_HOST, port=SERVER_PORT, reload=True)