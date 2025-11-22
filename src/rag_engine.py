# src/rag_engine.py
"""RAG検索エンジン：ベクトルDBから関連文書を取得してLLMで回答生成"""

from typing import Dict, Optional, Tuple
import logging

from langchain_openai import ChatOpenAI
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory

from src.utils import PERSIST_DIR, COLLECTION_NAME, get_embeddings, format_docs

# ===== ロガー設定 =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== 定数 =====
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TOP_K = 3
DEFAULT_SPEAKER = "高市早苗"

SYSTEM_PROMPT = """あなたは有能なアシスタントです。

【コンテキスト】
{context}

上記のコンテキストと会話履歴を参考に、高市早苗氏がどんな発言をしたかを、複数引用して2-3段落程度の文章で回答してください。
回答には必ず「高市早苗」というワードを回答に含めつつ、「発言日時」を明記してください。
コンテキストに情報がない場合は、あなたの一般知識で回答してください。
ユーザーが「これまでの質問を要約して」などと聞いた場合は、会話履歴から質問を抽出して要約してください。
"""


def load_vectorstore() -> Chroma:
    """既存の Chroma ベクトルDB を読み込む
    
    Returns:
        Chroma: ベクトルストアインスタンス
        
    Raises:
        RuntimeError: ベクトルDBが見つからない場合
    """
    if not PERSIST_DIR.exists():
        raise RuntimeError(f"ベクトルDBが見つかりません: {PERSIST_DIR}")
    
    embeddings = get_embeddings()
    vectordb = Chroma(
        persist_directory=str(PERSIST_DIR),
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
    )
    logger.info(f"ベクトルDBを読み込みました: {PERSIST_DIR}")
    return vectordb


def build_rag_chain_with_memory(
    vectordb: Chroma, 
    k: int = DEFAULT_TOP_K
) -> Tuple[RunnableWithMessageHistory, Dict[str, ChatMessageHistory]]:
    """メモリ付きRAGチェーンを構築
    
    Args:
        vectordb: ベクトルストア
        k: 検索する文書数
        
    Returns:
        Tuple[チェーン, 会話履歴ストア]
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}"),
    ])
    
    llm = ChatOpenAI(model=DEFAULT_MODEL, temperature=DEFAULT_TEMPERATURE)
    core_chain = prompt | llm | StrOutputParser()

    # セッションIDごとに会話履歴を保持
    store: Dict[str, ChatMessageHistory] = {}

    def get_session_history(session_id: str) -> ChatMessageHistory:
        if session_id not in store:
            store[session_id] = ChatMessageHistory()
        return store[session_id]

    chain_with_memory = RunnableWithMessageHistory(
        core_chain,
        get_session_history,
        input_messages_key="question",
        history_messages_key="chat_history",
    )
    return chain_with_memory, store


def diagnose_vectordb() -> None:
    """ベクトルDBの状態を診断（デバッグ用）"""
    logger.info("=" * 60)
    logger.info("ベクトルDB診断開始")
    logger.info("=" * 60)
    
    try:
        vectordb = load_vectorstore()
        collection = vectordb._collection
        count = collection.count()
        
        logger.info(f"コレクション名: {COLLECTION_NAME}")
        logger.info(f"保存パス: {PERSIST_DIR}")
        logger.info(f"ドキュメント数: {count}")
        
        if count == 0:
            logger.error("⚠️ ベクトルDBにドキュメントが登録されていません！")
            logger.info("前処理を実行してデータを登録してください")
            return
        
        # テストクエリ実行
        test_queries = ["高市早苗", "総理大臣", "経済政策"]
        
        for query in test_queries:
            logger.info(f"\n--- テストクエリ: '{query}' ---")
            retriever = vectordb.as_retriever(search_kwargs={"k": 3})
            docs = retriever.invoke(query)
            logger.info(f"検索結果: {len(docs)}件")
            
            if docs:
                logger.info(f"最初の結果（100文字）: {docs[0].page_content[:100]}...")
            else:
                logger.warning("検索結果なし")
        
        logger.info("\n" + "=" * 60)
        logger.info("診断完了")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"診断中にエラー: {e}")
        import traceback
        logger.error(traceback.format_exc())


def answer_question(
    question: str,
    top_k: int = DEFAULT_TOP_K,
    session_id: str = "default",
) -> Dict:
    """質問に回答するメイン関数
    
    Args:
        question: ユーザーの質問
        top_k: 検索する文書数
        session_id: セッションID（会話履歴の識別用）
        
    Returns:
        Dict: {"answer": 回答, "context_docs": 参照した文書リスト}
        
    Raises:
        RuntimeError: RAGエンジンが初期化されていない場合
    """
    if _vectordb is None or _chain is None:
        raise RuntimeError("RAGエンジンが初期化されていません")
    
    # 発言者でフィルタリング
    speaker_filter = {"speaker": DEFAULT_SPEAKER}
    retriever = _vectordb.as_retriever(
        search_kwargs={"k": top_k, "filter": speaker_filter}
    )
    
    docs = retriever.invoke(question)
    context_text = format_docs(docs)
    
    logger.info(f"生成されたコンテキストの長さ: {len(context_text)} 文字")
    
    response = _chain.invoke(
        {
            "context": context_text,
            "question": question,
        },
        config={
            "configurable": {
                "session_id": session_id,
            }
        },
    )
    
    return {
        "answer": response,
        "context_docs": [
            {
                "content": d.page_content,
                "source": d.metadata.get("source"),
            }
            for d in docs
        ],
    }


# ===== モジュール初期化 =====
_vectordb: Optional[Chroma] = None
_chain: Optional[RunnableWithMessageHistory] = None
_history_store: Optional[Dict[str, ChatMessageHistory]] = None

try:
    _vectordb = load_vectorstore()
    _chain, _history_store = build_rag_chain_with_memory(_vectordb)
    logger.info("RAGエンジンの初期化が完了しました")
except Exception as e:
    logger.error(f"RAGエンジンの初期化に失敗しました: {e}")
    raise