import os
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud.firestore_v1 import FieldFilter
from openai import OpenAI

from firebase_config import db

app = FastAPI(title="나만의 AI 비서")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DataItem(BaseModel):
    date: str
    value: float
    memo: str


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


@app.get("/")
def read_root():
    return {"message": "AI 비서 서버가 잘 작동하고 있어요!"}


# ============================================================
# 데이터 요약 만들기
# ============================================================
def build_summary():
    docs = db.collection("data").stream()
    rows = [doc.to_dict() for doc in docs]
    if not rows:
        return None

    rows.sort(key=lambda r: r["date"])
    dates = [r["date"] for r in rows]

    industries = {}
    for r in rows:
        industries.setdefault(r["memo"], []).append(r)

    def summarize(items):
        items = sorted(items, key=lambda r: r["date"])
        values = [r["value"] for r in items]
        n = len(values)
        avg = round(sum(values) / n, 1)
        recent = values[-30:]
        previous = values[-60:-30] if n >= 60 else values[:-30]
        trend = "유지"
        if previous:
            r_avg = sum(recent) / len(recent)
            p_avg = sum(previous) / len(previous)
            if r_avg > p_avg * 1.05:
                trend = "증가"
            elif r_avg < p_avg * 0.95:
                trend = "감소"
        return {
            "count": n,
            "average": avg,
            "max": round(max(values), 1),
            "min": round(min(values), 1),
            "trend": trend,
        }

    return {
        "period": f"{dates[0]} ~ {dates[-1]}",
        "count": len(rows),
        "unit": "네이버 데이터랩 상대지수(0~100, 최고=100)",
        "by_industry": {name: summarize(items) for name, items in industries.items()},
    }


def summary_to_text(summary):
    lines = [
        f"- 기간: {summary['period']} (총 {summary['count']}개)",
        f"- 값 단위: {summary['unit']}",
    ]
    for name, s in summary["by_industry"].items():
        lines.append(
            f"- {name}: 평균 {s['average']}, 최대 {s['max']}, 최소 {s['min']}, 최근추세 {s['trend']}"
        )
    return "\n".join(lines)


@app.get("/api/data/summary")
def get_summary():
    summary = build_summary()
    if summary is None:
        return {"message": "아직 데이터가 없어요"}
    return summary


# ============================================================
# 데이터 API (CRUD)
# ============================================================
@app.get("/api/data")
def get_data(memo: str | None = None, limit: int = 100):
    query = db.collection("data")
    if memo:
        query = query.where(filter=FieldFilter("memo", "==", memo))
    docs = query.limit(limit).stream()
    result = []
    for doc in docs:
        item = doc.to_dict()
        item["id"] = doc.id
        result.append(item)
    return {"count": len(result), "items": result}


@app.post("/api/data")
def create_data(item: DataItem):
    ref = db.collection("data").add(item.model_dump())
    return {"message": "저장했어요", "id": ref[1].id}


@app.put("/api/data/{doc_id}")
def update_data(doc_id: str, item: DataItem):
    ref = db.collection("data").document(doc_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="그런 데이터가 없어요")
    ref.set(item.model_dump())
    return {"message": "수정했어요", "id": doc_id}


@app.delete("/api/data/{doc_id}")
def delete_data(doc_id: str):
    ref = db.collection("data").document(doc_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="그런 데이터가 없어요")
    ref.delete()
    return {"message": "삭제했어요", "id": doc_id}


# ============================================================
# AI 채팅 API — 요약을 GPT에 주입해서 대화 + 자동 저장
#   * 문제 원인을 화면에 그대로 보여주도록 try/except 로 감쌈
# ============================================================
@app.post("/api/chat")
def chat(req: ChatRequest):
    try:
        summary = build_summary()
        if summary is None:
            raise HTTPException(status_code=400, detail="데이터가 없어 요약할 수 없어요")
        summary_text = summary_to_text(summary)

        system_prompt = (
            "당신은 경남 창원 지역 업종별 '네이버 검색 관심도' 데이터를 아는 친절한 분석 비서입니다. "
            "아래 데이터 요약을 근거로, 쉽고 구체적으로 한국어(존댓말)로 답하세요. "
            "데이터에 없는 내용은 아는 척하지 말고 모른다고 하세요.\n\n"
            f"[데이터 요약]\n{summary_text}"
        )

        conv_id = req.conversation_id
        history = []
        if conv_id:
            doc = db.collection("conversations").document(conv_id).get()
            if doc.exists:
                history = doc.to_dict().get("messages", [])

        messages = [{"role": "system", "content": system_prompt}]
        messages += history
        messages.append({"role": "user", "content": req.message})

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=400,
            temperature=0.5,
        )
        reply = completion.choices[0].message.content

        new_history = history + [
            {"role": "user", "content": req.message},
            {"role": "assistant", "content": reply},
        ]
        now = datetime.now().isoformat()
        if conv_id:
            db.collection("conversations").document(conv_id).set(
                {"messages": new_history, "updated_at": now}, merge=True
            )
        else:
            ref = db.collection("conversations").add(
                {"messages": new_history, "created_at": now, "updated_at": now}
            )
            conv_id = ref[1].id

        return {"conversation_id": conv_id, "reply": reply}

    except HTTPException:
        raise
    except Exception as e:
        # 진짜 원인을 화면(Response)에 그대로 보여줌
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
