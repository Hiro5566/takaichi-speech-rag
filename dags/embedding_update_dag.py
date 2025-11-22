# dags/embedding_update_dag.py

from datetime import datetime, timedelta
import os

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_ROOT = os.environ.get("RAG_PROJECT_ROOT", "/opt/airflow")
PYTHON_BIN = os.environ.get("RAG_PYTHON_BIN", "python")

# ==== DAG の共通設定 ====

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# スケジュール:
with DAG(
    dag_id="embedding_update_dag",
    default_args=default_args,
    start_date=datetime(2025, 1, 1),
    schedule_interval="8 2 * * *",  # 毎日 03:00 (UTC)
    catchup=False,
    tags=["rag", "diet", "chroma"],
) as dag:

    # 1. 国会議事録の最新JSONLを取得するタスク
    fetch_diet_speeches = BashOperator(
        task_id="fetch_diet_speeches",
        bash_command=(
            f"cd {PROJECT_ROOT} && "
            f"PYTHONUNBUFFERED=1 {PYTHON_BIN} src/get_diet_speeches.py"
        ),
    )

    # 2. JSONL → ベクトルDB更新（update_vectorstore.py）
    update_vectorstore = BashOperator(
        task_id="update_vectorstore",
        bash_command=(
            f"cd {PROJECT_ROOT} && "
            f"PYTHONUNBUFFERED=1 {PYTHON_BIN} src/update_vectorstore.py"
        ),
    )

    # 実行順序: get_diet_speeches → update_vectorstore
    fetch_diet_speeches >> update_vectorstore
