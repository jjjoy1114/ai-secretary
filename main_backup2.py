from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud.firestore_v1 import FieldFilter

from firebase_config import db

# 우리 AI 비서의 '본체'를 하나 만들어요
app = FastAPI(title="나만의 AI 비서")

# CORS 설정 = 나중에 웹페이지가 이 서버에 접속하도록 문을 열어두는 부분
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 지금은 개발 중이라 모두 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 데이터 모양 정의 (Pydantic) — 들어온 데이터가 올바른지 자동으로 검사해줌
# ============================================================
class DataItem(BaseModel):
    date: str     # 예: "2025-09-09"
    value: float  # 예: 35.8 (네이버 데이터랩 상대지수 0~100)
    memo: str     # 예: "카페" (업종)


# 기본 주소("/") — 서버가 잘 살아있는지 확인하는 창구
@app.get("/")
def read_root():
    return {"message": "AI 비서 서버가 잘 작동하고 있어요!"}


# ============================================================
# 데이터 요약 API — 1,098개를 짧게 정리 (AI에게 귀띔해줄 핵심 재료)
#   * 주의: /{doc_id} 보다 먼저 선언해야 'summary'가 문서ID로 오해받지 않아요
# ============================================================
@app.get("/api/data/summary")
def get_summary():
    docs = db.collection("data").stream()
    rows = [doc.to_dict() for doc in docs]

    if not rows:
        return {"message": "아직 데이터가 없어요"}

    rows.sort(key=lambda r: r["date"])          # 날짜 순 정렬
    dates = [r["date"] for r in rows]

    # 업종별로 나눠 담기
    industries = {}
    for r in rows:
        industries.setdefault(r["memo"], []).append(r)

    def summarize(items):
        items = sorted(items, key=lambda r: r["date"])
        values = [r["value"] for r in items]
        n = len(values)
        avg = round(sum(values) / n, 1)
        # 최근 추세 = 마지막 30일 평균 vs 그 앞 30일 평균
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

    by_industry = {name: summarize(items) for name, items in industries.items()}

    return {
        "period": f"{dates[0]} ~ {dates[-1]}",
        "count": len(rows),
        "unit": "네이버 데이터랩 상대지수(0~100, 최고=100)",
        "by_industry": by_industry,
    }


# ============================================================
# 데이터 API (CRUD) — 창고의 데이터를 다루는 창구 4개
# ============================================================

# (R·Read) 데이터 목록 보기
@app.get("/api/data")
def get_data(memo: str | None = None, limit: int = 100):
    query = db.collection("data")
    if memo:  # 업종으로 걸러보기 (선택 사항)
        query = query.where(filter=FieldFilter("memo", "==", memo))
    docs = query.limit(limit).stream()
    result = []
    for doc in docs:
        item = doc.to_dict()
        item["id"] = doc.id       # 문서 고유번호도 같이 넣어줌
        result.append(item)
    return {"count": len(result), "items": result}


# (C·Create) 데이터 추가
@app.post("/api/data")
def create_data(item: DataItem):
    ref = db.collection("data").add(item.model_dump())
    # add()는 (저장시간, 문서참조)를 돌려줘요 → [1]이 문서참조
    return {"message": "저장했어요", "id": ref[1].id}


# (U·Update) 데이터 수정
@app.put("/api/data/{doc_id}")
def update_data(doc_id: str, item: DataItem):
    ref = db.collection("data").document(doc_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="그런 데이터가 없어요")
    ref.set(item.model_dump())
    return {"message": "수정했어요", "id": doc_id}


# (D·Delete) 데이터 삭제
@app.delete("/api/data/{doc_id}")
def delete_data(doc_id: str):
    ref = db.collection("data").document(doc_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="그런 데이터가 없어요")
    ref.delete()
    return {"message": "삭제했어요", "id": doc_id}
