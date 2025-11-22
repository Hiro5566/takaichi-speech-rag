# src/get_diet_speeches.py
"""国会議事録APIからデータを取得するスクリプト"""

import requests
import time
import json
from pathlib import Path
import math
from datetime import date, timedelta
from typing import Optional, Set

# ===== 設定 =====
BASE_URL = "https://kokkai.ndl.go.jp/api/speech"
BASE_DIR = Path(__file__).resolve().parent.parent  # プロジェクトルート

OUT_DIR = BASE_DIR / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_PATH = OUT_DIR / "diet_speeches.jsonl"
STATE_PATH = OUT_DIR / "fetch_state.json"
IDS_PATH = OUT_DIR / "fetched_ids.txt"

INIT_FROM_DATE = date(2023, 1, 1)
REQUEST_INTERVAL = 1  # APIリクエスト間隔（秒）
MAX_RECORDS_PER_REQUEST = 100


def load_state() -> dict:
    """取得状態を読み込む"""
    if STATE_PATH.exists():
        with STATE_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_fetched_date": None}


def save_state(last_date: str) -> None:
    """取得状態を保存"""
    with STATE_PATH.open("w", encoding="utf-8") as f:
        json.dump({"last_fetched_date": last_date}, f, ensure_ascii=False)


def load_fetched_ids() -> Set[str]:
    """取得済みIDを読み込む"""
    if not IDS_PATH.exists():
        return set()
    with IDS_PATH.open("r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())


def save_fetched_ids(ids: Set[str]) -> None:
    """取得済みIDを保存"""
    with IDS_PATH.open("w", encoding="utf-8") as f:
        for id_ in ids:
            f.write(id_ + "\n")


def append_fetched_ids(new_ids: Set[str]) -> None:
    """取得済みIDを追記"""
    with IDS_PATH.open("a", encoding="utf-8") as f:
        for id_ in new_ids:
            f.write(id_ + "\n")


def get_record_count(from_str: str, until_str: str) -> int:
    """指定期間のレコード件数を取得"""
    params = {
        "from": from_str,
        "until": until_str,
        "nameOfMeeting": "本会議 予算委員会 総務委員会",
        "maximumRecords": 1,
        "recordPacking": "json",
    }
    r = requests.get(BASE_URL, params=params)
    r.raise_for_status()
    return int(r.json().get("numberOfRecords", 0))


def fetch_initial(from_date: date, to_date: date) -> Optional[str]:
    """
    初回取得: メモリに溜めずに直接JSONLへストリーム書き込み
    
    Returns:
        取得した最新日付（データがなければNone）
    """
    from_str = from_date.isoformat()
    until_str = to_date.isoformat()
    
    print(f"件数確認中... {from_str} 〜 {until_str}")
    total = get_record_count(from_str, until_str)
    print(f"検索結果件数: {total}")
    
    if total == 0:
        print("データなし。")
        return None
    
    params = {
        "from": from_str,
        "until": until_str,
        "nameOfMeeting": "本会議 予算委員会 総務委員会",
        "maximumRecords": MAX_RECORDS_PER_REQUEST,
        "recordPacking": "json",
    }
    
    pages = math.ceil(total / MAX_RECORDS_PER_REQUEST)
    fetched = 0
    latest_date = None
    all_ids: Set[str] = set()
    
    with OUT_PATH.open("w", encoding="utf-8") as f_out:
        for i in range(pages):
            start_record = 1 + i * MAX_RECORDS_PER_REQUEST
            if start_record > total:
                break
            
            params["startRecord"] = start_record
            r = requests.get(BASE_URL, params=params)
            r.raise_for_status()
            data = r.json()
            
            speech_records = data.get("speechRecord", [])
            if isinstance(speech_records, dict):
                speech_records = [speech_records]
            
            for rec in speech_records:
                f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fetched += 1
                
                speech_id = rec.get("speechID")
                if speech_id:
                    all_ids.add(speech_id)
                
                rec_date = rec.get("date")
                if rec_date and (latest_date is None or rec_date > latest_date):
                    latest_date = rec_date
            
            print(f"\r取得中... {fetched}/{total}", end="", flush=True)
            time.sleep(REQUEST_INTERVAL)
    
    save_fetched_ids(all_ids)
    
    print(f"\n✅ 初回取得完了: {fetched}件")
    return latest_date


def fetch_incremental(from_date: date, to_date: date) -> Optional[str]:
    """
    差分取得: IDファイルでチェックして重複を避ける
    
    Returns:
        取得した最新日付（新規データがなければNone）
    """
    from_str = from_date.isoformat()
    until_str = to_date.isoformat()
    
    existing_ids = load_fetched_ids()
    print(f"重複チェック用ID数: {len(existing_ids)}")
    
    print(f"件数確認中... {from_str} 〜 {until_str}")
    total = get_record_count(from_str, until_str)
    print(f"検索結果件数: {total}")
    
    if total == 0:
        print("新規データなし。")
        return None
    
    params = {
        "from": from_str,
        "until": until_str,
        "nameOfMeeting": "本会議 予算委員会 総務委員会",
        "maximumRecords": MAX_RECORDS_PER_REQUEST,
        "recordPacking": "json",
    }
    
    pages = math.ceil(total / MAX_RECORDS_PER_REQUEST)
    new_count = 0
    latest_date = None
    new_ids: Set[str] = set()
    
    with OUT_PATH.open("a", encoding="utf-8") as f_out:
        for i in range(pages):
            start_record = 1 + i * MAX_RECORDS_PER_REQUEST
            if start_record > total:
                break
            
            params["startRecord"] = start_record
            r = requests.get(BASE_URL, params=params)
            r.raise_for_status()
            data = r.json()
            
            speech_records = data.get("speechRecord", [])
            if isinstance(speech_records, dict):
                speech_records = [speech_records]
            
            for rec in speech_records:
                speech_id = rec.get("speechID")
                
                # 重複スキップ
                if speech_id and speech_id in existing_ids:
                    continue
                
                f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                new_count += 1
                
                if speech_id:
                    existing_ids.add(speech_id)
                    new_ids.add(speech_id)
                
                rec_date = rec.get("date")
                if rec_date and (latest_date is None or rec_date > latest_date):
                    latest_date = rec_date
            
            print(f"\r取得中... {start_record}/{total} (新規: {new_count}件)", end="", flush=True)
            time.sleep(REQUEST_INTERVAL)
    
    if new_ids:
        append_fetched_ids(new_ids)
    
    print(f"\n✅ 差分取得完了: {new_count}件追加")
    return latest_date


def auto_fetch() -> None:
    """
    自動判定して取得を実行
    - JSONLなし → 初回取得
    - JSONLあり → 差分取得
    """
    today = date.today()
    state = load_state()
    
    if not OUT_PATH.exists() or OUT_PATH.stat().st_size == 0:
        print("=== 初回取得モード ===")
        latest = fetch_initial(INIT_FROM_DATE, today)
    else:
        print("=== 差分取得モード ===")
        if state["last_fetched_date"]:
            from_date = date.fromisoformat(state["last_fetched_date"]) - timedelta(days=3)
        else:
            from_date = INIT_FROM_DATE
        
        latest = fetch_incremental(from_date, today)
    
    if latest:
        save_state(latest)
        print(f"状態保存: last_fetched_date = {latest}")
    
    print(f"保存先: {OUT_PATH.resolve()}")


if __name__ == "__main__":
    auto_fetch()