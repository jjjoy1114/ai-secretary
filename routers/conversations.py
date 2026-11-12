"""대화기록 API — 저장된 대화를 목록/불러오기/저장/삭제."""
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from google.cloud import firestore

from firebase_config import db
from schemas import ConversationCreate

router = APIRouter()


# (목록) 저장된 대화 목록 보기 (최신순, 제목=첫 질문) — 최근 limit개만 가져와요 (대화가 쌓여도 읽기 비용이 일정)
@router.get("/api/conversations")
def list_conversations(limit: int = Query(default=50, ge=1, le=200)):
    docs = (db.collection("conversations")
            .order_by("updated_at", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream())
    result = []
    for doc in docs:
        d = doc.to_dict()
        msgs = d.get("messages", [])
        first_q = next((m["content"] for m in msgs if m.get("role") == "user"), "(빈 대화)")
        result.append({
            "id": doc.id,
            "title": first_q[:30],            # 목록에 보여줄 짧은 제목
            "updated_at": d.get("updated_at"),
            "count": len(msgs),
        })
    return {"count": len(result), "items": result}


# (불러오기) 특정 대화의 전체 메시지 보기
@router.get("/api/conversations/{conv_id}")
def get_conversation(conv_id: str):
    doc = db.collection("conversations").document(conv_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="그런 대화가 없어요")
    d = doc.to_dict()
    d["id"] = doc.id
    return d


# (저장) 대화를 직접 저장 (챗봇은 자동 저장하지만, 요구사항 충족용)
@router.post("/api/conversations")
def create_conversation(conv: ConversationCreate):
    now = datetime.now().isoformat()
    ref = db.collection("conversations").add({
        "messages": conv.messages,
        "created_at": now,
        "updated_at": now,
    })
    return {"message": "저장했어요", "id": ref[1].id}


# (삭제) 대화 삭제
@router.delete("/api/conversations/{conv_id}")
def delete_conversation(conv_id: str):
    ref = db.collection("conversations").document(conv_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="그런 대화가 없어요")
    ref.delete()
    return {"message": "삭제했어요", "id": conv_id}
