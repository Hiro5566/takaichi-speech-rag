# ========== ベースイメージ ==========
FROM python:3.10-slim

# ========== 作業ディレクトリ ==========
WORKDIR /app

# ========== 依存関係のインストール ==========
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ========== ソースコード/データのコピー ==========
COPY src ./src
COPY data ./data

# ========== 環境変数（OpenAI APIキーはHF上で設定する） ==========
ENV PYTHONUNBUFFERED=1

# ========== ベクトルDBの作成 ==========
# RUN python -m src.get_diet_speeches
# RUN python -m src.update_vectorstore

# ========== アプリケーション起動 ==========
# グラディオUI（ui_gradio.py）を起動する場合：
CMD ["python", "-m", "src.ui_gradio"]

# ===== FastAPIを起動したい場合はこちら（コメント切替） =====
# CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
