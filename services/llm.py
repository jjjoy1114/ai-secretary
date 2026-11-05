"""GPT 호출(코디세이 게이트웨이) + 대화 기록 불러오기/저장 — 채팅·에이전트가 같이 써요."""
import os
from datetime import datetime

from openai import OpenAI

from firebase_config import db

MODEL = "gpt-5-mini"     # 코디세이 콘솔에서 사용 가능한 모델


def get_client():
    return OpenAI(
        api_key=os.getenv("CODYSSEY_API_KEY"),          # 코디세이 발급 키
        base_url="https://copa.codyssey.kr/v1",          # 코디세이 OpenAI 호환 게이트웨이
    )


def load_history(conv_id):
    """저장된 대화가 있으면 메시지 목록을, 없으면 빈 목록을 돌려줘요."""
    if conv_id:
        doc = db.collection("conversations").document(conv_id).get()
        if doc.exists:
            return doc.to_dict().get("messages", [])
    return []


def save_turn(conv_id, history, user_message, reply):
    """질문·답변 한 쌍을 대화에 이어 붙여 저장하고, 대화 번호를 돌려줘요(새 대화면 새로 만듦)."""
    new_history = history + [
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": reply},
    ]
    now = datetime.now().isoformat()
    if conv_id:
        db.collection("conversations").document(conv_id).set(
            {"messages": new_history, "updated_at": now}, merge=True
        )
        return conv_id
    ref = db.collection("conversations").add(
        {"messages": new_history, "created_at": now, "updated_at": now}
    )
    return ref[1].id
