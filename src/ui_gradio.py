# src/ui_gradio.py
"""Gradio UIでのチャットインターフェース"""

from typing import List, Dict, Tuple
import gradio as gr

from src.rag_engine import answer_question

# ===== 定数 =====
DEFAULT_TOP_K = 10
SERVER_NAME = "0.0.0.0"
SERVER_PORT = 7860


def chat_fn(
    message: str, 
    history: List[Dict], 
    top_k: int
) -> Tuple[List[Dict], List[Dict]]:
    """
    Gradioから呼ばれるチャット関数
    
    Args:
        message: ユーザーの入力テキスト
        history: これまでの会話履歴
        top_k: 検索する文書数
        
    Returns:
        Tuple[更新後の履歴, State用の履歴]
    """
    if history is None:
        history = []

    # ユーザーメッセージを履歴に追加
    history.append({"role": "user", "content": message})

    result = answer_question(
        question=message,
        top_k=int(top_k),
        session_id="default",
    )
    answer = result.get("answer", "")

    # アシスタントの応答を履歴に追加
    history.append({"role": "assistant", "content": answer})

    return history, history


def clear_history() -> Tuple[List, List]:
    """会話履歴をクリア"""
    return [], []


def build_demo() -> gr.Blocks:
    """Gradio UI全体を組み立てる"""
    with gr.Blocks(title="高市早苗 国会発言検索") as demo:
        gr.Markdown("""
# 🤖 高市早苗 国会発言検索チャットボット

2023年以降の国会会議録データから高市氏の発言を検索します。

**検索例**
- スパイ
- 安全保障
- 存立危機事態
        """)

        with gr.Row():
            top_k_slider = gr.Slider(
                minimum=1,
                maximum=20,
                value=DEFAULT_TOP_K,
                step=1,
                label="検索する文書数 (top_k)",
                info="ベクトル検索で取得する関連文書数",
            )

        chatbot = gr.Chatbot(
            label="チャット", 
            height=500, 
        )
        
        textbox = gr.Textbox(
            label="質問を入力して Enter",
            placeholder="例）安全保障について教えて",
        )
        
        with gr.Row():
            submit_btn = gr.Button("送信", variant="primary")
            clear_btn = gr.Button("履歴クリア")

        # 会話履歴を保持するState
        history_state = gr.State([])

        # イベントハンドラ
        submit_btn.click(
            fn=chat_fn,
            inputs=[textbox, history_state, top_k_slider],
            outputs=[chatbot, history_state],
        )

        textbox.submit(
            fn=chat_fn,
            inputs=[textbox, history_state, top_k_slider],
            outputs=[chatbot, history_state],
        )

        clear_btn.click(
            fn=clear_history, 
            outputs=[chatbot, history_state]
        )

    return demo


# アプリ作成
demo = build_demo()

if __name__ == "__main__":
    demo.launch(server_name=SERVER_NAME, server_port=SERVER_PORT)