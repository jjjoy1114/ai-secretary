import os
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google.cloud.firestore_v1 import FieldFilter
from openai import OpenAI

from firebase_config import db
from kosis_client import fetch_changwon_population, KosisError, MEMO as POP_MEMO

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
# 창원시 인구 API — KOSIS(국가통계포털) 공공데이터 연동
#   * 'population' 컬렉션에 따로 저장 (검색 관심도 데이터와 섞이지 않게)
#   * 문서 ID = 'YYYY-MM' → 같은 달은 덮어쓰기라서 여러 번 눌러도 중복이 안 생겨요
# ============================================================
@app.post("/api/population/refresh")
def refresh_population(months: int = 60):
    """KOSIS에서 최신 창원시 월별 인구를 받아와 Firestore에 저장(없으면 추가, 있으면 갱신)."""
    try:
        rows = fetch_changwon_population(months)
    except KosisError as e:
        raise HTTPException(status_code=502, detail=str(e))

    col = db.collection("population")
    existing = {doc.id for doc in col.stream()}
    batch = db.batch()
    for r in rows:
        batch.set(col.document(r["date"]), r)
    batch.commit()

    new_count = len([r for r in rows if r["date"] not in existing])
    db.collection("sync_log").document("population").set({
        "source": "KOSIS DT_1B040A3 (행정안전부 주민등록인구)",
        "refreshed_at": datetime.now().isoformat(),
        "latest_month": rows[-1]["date"] if rows else None,
        "count": len(rows),
    })
    return {
        "message": "KOSIS에서 최신 인구 데이터를 받아 저장했어요",
        "received": len(rows),
        "new": new_count,
        "updated": len(rows) - new_count,
        "period": f"{rows[0]['date']} ~ {rows[-1]['date']}" if rows else None,
    }


@app.get("/api/population")
def get_population():
    docs = db.collection("population").stream()
    items = sorted((d.to_dict() for d in docs), key=lambda r: r["date"])
    return {"count": len(items), "items": items}


def build_population_summary():
    docs = db.collection("population").stream()
    rows = sorted((d.to_dict() for d in docs), key=lambda r: r["date"])
    if not rows:
        return None
    first, last = rows[0], rows[-1]
    values = [r["value"] for r in rows]

    # 1년 전 같은 달과 비교
    year_ago = next((r for r in rows if r["date"] == f"{int(last['date'][:4]) - 1}{last['date'][4:]}"), None)
    yoy = last["value"] - year_ago["value"] if year_ago else None

    # 100만 명 아래로 처음 내려간 달 (창원시는 '특례시' 기준이 인구 100만이라 의미 있는 지점)
    below_1m = next((r["date"] for r in rows if r["value"] < 1_000_000), None)

    sync = db.collection("sync_log").document("population").get()
    return {
        "region": "경상남도 창원시",
        "period": f"{first['date']} ~ {last['date']}",
        "count": len(rows),
        "unit": "명 (주민등록인구, 월말 기준)",
        "latest": {"date": last["date"], "value": last["value"]},
        "change_total": last["value"] - first["value"],
        "change_rate_total": round((last["value"] - first["value"]) / first["value"] * 100, 2),
        "change_1year": yoy,
        "avg_monthly_change": round((last["value"] - first["value"]) / max(len(rows) - 1, 1)),
        "max": max(values),
        "min": min(values),
        "first_month_below_1m": below_1m,
        "source": "KOSIS 국가통계포털 (행정안전부 주민등록인구통계)",
        "refreshed_at": sync.to_dict().get("refreshed_at") if sync.exists else None,
    }


def population_summary_to_text(p):
    lines = [
        f"- 지역: {p['region']}, 기간: {p['period']} (월별 {p['count']}개), 단위: {p['unit']}",
        f"- 최근({p['latest']['date']}) 인구: {p['latest']['value']:,}명",
        f"- 기간 전체 변화: {p['change_total']:+,}명 ({p['change_rate_total']:+}%), 월평균 {p['avg_monthly_change']:+,}명",
    ]
    if p["change_1year"] is not None:
        lines.append(f"- 최근 1년 변화: {p['change_1year']:+,}명")
    if p["first_month_below_1m"]:
        lines.append(f"- 인구 100만 명 아래로 처음 내려간 달: {p['first_month_below_1m']}")
    lines.append(f"- 출처: {p['source']}")
    return "\n".join(lines)


@app.get("/api/population/summary")
def get_population_summary():
    p = build_population_summary()
    if p is None:
        return {"message": "아직 인구 데이터가 없어요. POST /api/population/refresh 를 먼저 실행해 주세요"}
    return p


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

        pop = build_population_summary()
        pop_text = population_summary_to_text(pop) if pop else "- (아직 인구 데이터 없음)"

        system_prompt = (
            "당신은 경남 창원 지역 소상공인을 돕는 친절한 데이터 분석 비서입니다. "
            "두 가지 데이터를 알고 있어요: ① 창원 업종별 '네이버 검색 관심도'(상대지수) "
            "② 창원시 월별 주민등록인구(KOSIS 공공데이터). "
            "아래 요약을 근거로, 쉽고 구체적으로 한국어(존댓말)로 답하세요. "
            "두 데이터를 함께 해석할 때는 '관련이 있을 수 있다' 수준으로 조심스럽게 말하고, "
            "데이터에 없는 내용은 아는 척하지 말고 모른다고 하세요.\n\n"
            f"[① 검색 관심도 요약]\n{summary_text}\n\n"
            f"[② 창원시 인구 요약]\n{pop_text}"
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

        client = OpenAI(
            api_key=os.getenv("CODYSSEY_API_KEY"),          # 코디세이 발급 키
            base_url="https://copa.codyssey.kr/v1",          # 코디세이 OpenAI 호환 게이트웨이
        )
        completion = client.chat.completions.create(
            model="gpt-5-mini",     # 코디세이 콘솔에서 사용 가능한 모델
            messages=messages,
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


# ============================================================
# 대화기록 API — 저장된 대화를 목록/불러오기/삭제
# ============================================================
class ConversationCreate(BaseModel):
    messages: list  # [{"role": "...", "content": "..."} , ...]


# (목록) 저장된 대화 목록 보기 (최신순, 제목=첫 질문)
@app.get("/api/conversations")
def list_conversations():
    docs = db.collection("conversations").stream()
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
    result.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    return {"count": len(result), "items": result}


# (불러오기) 특정 대화의 전체 메시지 보기
@app.get("/api/conversations/{conv_id}")
def get_conversation(conv_id: str):
    doc = db.collection("conversations").document(conv_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="그런 대화가 없어요")
    d = doc.to_dict()
    d["id"] = doc.id
    return d


# (저장) 대화를 직접 저장 (챗봇은 자동 저장하지만, 요구사항 충족용)
@app.post("/api/conversations")
def create_conversation(conv: ConversationCreate):
    now = datetime.now().isoformat()
    ref = db.collection("conversations").add({
        "messages": conv.messages,
        "created_at": now,
        "updated_at": now,
    })
    return {"message": "저장했어요", "id": ref[1].id}


# (삭제) 대화 삭제
@app.delete("/api/conversations/{conv_id}")
def delete_conversation(conv_id: str):
    ref = db.collection("conversations").document(conv_id)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="그런 대화가 없어요")
    ref.delete()
    return {"message": "삭제했어요", "id": conv_id}


# ============================================================
# (보너스) 추가 통계 지표 — 업종별 월별 평균(그래프용) + 변동성·격차
# ============================================================
@app.get("/api/data/statistics")
def get_statistics():
    import statistics as st
    from collections import defaultdict
    rows = [d.to_dict() for d in db.collection("data").stream()]
    if not rows:
        return {"message": "데이터가 없어요"}

    monthly = defaultdict(lambda: defaultdict(list))  # 업종 -> 월 -> [값]
    by_ind = defaultdict(list)
    for r in rows:
        memo = r["memo"]; month = str(r["date"])[:7]; v = float(r["value"])
        monthly[memo][month].append(v)
        by_ind[memo].append(v)

    monthly_out = {}
    for memo, mm in monthly.items():
        monthly_out[memo] = [
            {"month": m, "avg": round(sum(vs) / len(vs), 1)} for m, vs in sorted(mm.items())
        ]

    std_out = {memo: round(st.pstdev(vs), 1) for memo, vs in by_ind.items()}  # 변동성
    avgs = {memo: sum(vs) / len(vs) for memo, vs in by_ind.items()}
    gap = round(max(avgs.values()) - min(avgs.values()), 1)                   # 업종간 격차
    top = max(avgs, key=avgs.get)

    return {
        "monthly": monthly_out,
        "변동성_표준편차": std_out,
        "업종간_평균격차": gap,
        "최고관심_업종": top,
    }
