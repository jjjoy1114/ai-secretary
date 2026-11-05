import os
import logging
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from google.cloud.firestore_v1 import FieldFilter
from openai import OpenAI

from firebase_config import db
from kosis_client import fetch_changwon_population, KosisError, MEMO as POP_MEMO

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ai-secretary")   # 서버 기록(Render의 Logs 화면에서 볼 수 있어요)

app = FastAPI(title="나만의 AI 비서")


# ============================================================
# 설정값 — 환경변수로 바꿀 수 있고, 적지 않으면 기본값을 써요
#   ALLOWED_ORIGINS    : CORS 허용 주소(쉼표로 여러 개). 기본 "*" = 모두 허용(데모·채점용)
#   SUMMARY_RECENT_DAYS: 추세 비교에 쓰는 '최근 N일' (기본 30 → 최근30일 vs 그 앞 30일)
#   MAX_TOKENS         : GPT 답변 길이 상한(비용 보호). 기본 0 = 제한 안 함
# ============================================================
def _env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()] or ["*"]
SUMMARY_RECENT_DAYS = max(1, _env_int("SUMMARY_RECENT_DAYS", 30))
MAX_TOKENS = _env_int("MAX_TOKENS", 0)


def token_limit():
    """MAX_TOKENS를 정했을 때만 GPT 호출에 길이 상한을 붙여요."""
    return {"max_completion_tokens": MAX_TOKENS} if MAX_TOKENS > 0 else {}

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DataItem(BaseModel):
    """데이터 1건 — 서버가 들어오는 값을 먼저 검사해요(Pydantic)."""
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$", description="날짜 (YYYY-MM-DD)", examples=["2026-09-09"])
    value: float = Field(ge=0, le=100, description="검색 관심도 상대지수 (0~100)", examples=[35.8])
    memo: str = Field(
        min_length=1, max_length=30,
        pattern=r"^[가-힣A-Za-z0-9][가-힣A-Za-z0-9 /·_\-]*$",
        description="업종 이름 — 한글·영문·숫자·공백·/ 만 허용(첫 글자는 글자나 숫자)",
        examples=["카페"],
    )

    @field_validator("date")
    @classmethod
    def date_must_exist(cls, v):
        datetime.strptime(v, "%Y-%m-%d")      # 2026-13-45 같은 없는 날짜는 여기서 걸러져요
        return v


# 검사에 걸렸을 때 영어 대신 알기 쉬운 한글로 알려주기
FIELD_NAMES = {"date": "날짜", "value": "값", "memo": "업종", "message": "메시지", "industry": "업종",
               "season": "시즌", "channel": "채널", "product": "상품", "conversation_id": "대화 번호", "messages": "메시지 목록"}
PATTERN_HINTS = {"date": "형식이 맞지 않아요 (예: 2026-09-09)",
                 "memo": "한글·영문·숫자·공백·/ 만 쓸 수 있어요 (예: 미용/뷰티)"}
ERROR_TEXTS = {
    "missing": "꼭 입력해야 해요",
    "string_pattern_mismatch": "형식이 맞지 않아요 (예: 2026-09-09)",
    "greater_than_equal": "0 이상이어야 해요",
    "less_than_equal": "100 이하여야 해요",
    "string_too_short": "비워둘 수 없어요",
    "string_too_long": "너무 길어요",
    "float_parsing": "숫자로 적어 주세요",
    "string_type": "글자로 적어 주세요",
    "value_error": "올바른 값이 아니에요 (날짜라면 실제 있는 날짜로, 예: 2026-09-09)",
    "too_long": "항목이 너무 많아요",
}


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    problems = []
    for e in exc.errors():
        loc = [str(x) for x in e.get("loc", []) if x not in ("body", "query", "path")]
        name = FIELD_NAMES.get(loc[-1], loc[-1]) if loc else "입력"
        if e.get("type") == "string_pattern_mismatch":
            text = PATTERN_HINTS.get(loc[-1] if loc else "", "허용되지 않는 글자가 있어요")
        else:
            text = ERROR_TEXTS.get(e.get("type"), str(e.get("msg", "확인이 필요해요")))
        problems.append(f"{name}: {text}")
    # 서버 기록에는 '어떤 칸이 왜 걸렸는지'만 남겨요 (입력한 내용·질문 본문은 남기지 않아요)
    logger.warning("입력 검증 실패 %s %s → %s", request.method, request.url.path, " / ".join(problems))
    return JSONResponse(
        status_code=422,
        content={"detail": "입력값을 확인해 주세요 → " + " / ".join(problems), "errors": problems},
    )


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000, description="질문 (1~1,000자)")
    conversation_id: str | None = Field(default=None, max_length=100)


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
        days = SUMMARY_RECENT_DAYS            # 기본 30일 — 환경변수 SUMMARY_RECENT_DAYS로 조정
        recent = values[-days:]
        previous = values[-2 * days:-days] if n >= 2 * days else values[:-days]
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
            **token_limit(),
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
    messages: list = Field(max_length=200)  # [{"role": "...", "content": "..."} , ...] (최대 200개)


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


# ============================================================
# 보너스 과제 A — AI 도구 호출 (Function Calling)
#   기존 /api/chat 은 요약을 '통째로' 시스템 프롬프트에 주입한다.
#   여기 /api/agent 는 GPT가 질문을 보고 '필요한 도구(함수)'를
#   스스로 골라 호출한 뒤, 그 결과로 답한다. → 진짜 '에이전트(비서)'
# ============================================================

# (1) GPT에게 건네줄 '도구 설명서' — 각 도구를 언제 쓰는지 알려준다
AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_search_summary",
            "description": (
                "창원 업종별 '네이버 검색 관심도'(상대지수 0~100) 전체 요약을 돌려준다. "
                "기간, 데이터 개수, 업종별 평균/최대/최소, 최근 추세(증가/감소/유지) 포함. "
                "사용자가 검색 관심도·인기·추세·업종 평균을 물으면 사용한다."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_statistics",
            "description": (
                "업종별 심화 통계를 돌려준다. 월별 평균 추이, 변동성(표준편차), "
                "업종 간 평균 격차, 가장 관심도가 높은 업종. "
                "'변동이 큰/작은', '격차', '어느 업종이 제일', '월별 흐름'을 물으면 사용한다."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_population_summary",
            "description": (
                "창원시 월별 주민등록인구(KOSIS 공공데이터) 요약을 돌려준다. "
                "최근 인구 수와 증감 추세 포함. 사용자가 인구·인구 변화를 물으면 사용한다."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


# (2) 도구 이름이 오면 실제 우리 함수를 실행해 결과(문자열)를 돌려준다
def run_agent_tool(name: str) -> str:
    if name == "get_search_summary":
        s = build_summary()
        return summary_to_text(s) if s else "검색 관심도 데이터가 없어요."
    if name == "get_statistics":
        return str(get_statistics())
    if name == "get_population_summary":
        p = build_population_summary()
        return population_summary_to_text(p) if p else "인구 데이터가 없어요."
    return f"'{name}'은(는) 알 수 없는 도구예요."


@app.post("/api/agent")
def agent(req: ChatRequest):
    """GPT가 필요한 도구를 스스로 호출해서 답하는 '에이전트' 채팅."""
    try:
        system_prompt = (
            "당신은 경남 창원 지역 소상공인을 돕는 친절한 데이터 분석 비서입니다. "
            "답하기 전에, 필요한 수치가 있으면 반드시 제공된 도구(함수)를 호출해 "
            "실제 데이터를 확인한 뒤 답하세요. 추측으로 숫자를 지어내지 말고, "
            "한국어 존댓말로 쉽고 구체적으로 답하세요."
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
            api_key=os.getenv("CODYSSEY_API_KEY"),
            base_url="https://copa.codyssey.kr/v1",
        )

        tools_used = []   # 어떤 도구를 불렀는지 기록 (보고서 증거용)
        reply = ""

        # GPT <-> 도구 호출을 최대 5번까지 주고받는다
        for _ in range(5):
            completion = client.chat.completions.create(
                model="gpt-5-mini",
                messages=messages,
                tools=AGENT_TOOLS,
                **token_limit(),
            )
            msg = completion.choices[0].message

            # 더 이상 도구가 필요 없으면 -> 최종 답변 완성
            if not msg.tool_calls:
                reply = msg.content or ""
                break

            # GPT가 도구를 부름 -> 실행해서 결과를 다시 GPT에게 전달
            messages.append(msg)
            for tc in msg.tool_calls:
                result = run_agent_tool(tc.function.name)
                tools_used.append(tc.function.name)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
        else:
            reply = "도구를 너무 많이 호출해서 멈췄어요. 질문을 조금 더 간단히 해주세요."

        # 대화 저장 (기존 /api/chat 과 같은 형식 — 프론트/기록과 호환)
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

        return {"conversation_id": conv_id, "reply": reply, "tools_used": tools_used}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


# ============================================================
# 콘텐츠 추천 도구 — 업종 데이터(성수기·변동성·관심도) + 창원 인구 맥락을
#   GPT에 주입해 SNS 콘텐츠·마케팅 기획안을 자동 생성한다. (SNS 대행 영업용)
# ============================================================
class ContentPlanRequest(BaseModel):
    industry: str = Field(min_length=1, max_length=30)          # 카페 / 미용/뷰티 / 미용의료 (memo 값, 부분입력 OK)
    season: str | None = Field(default=None, max_length=30)     # 예: 할로윈, 연말, 봄 (선택)
    channel: str | None = Field(default=None, max_length=30)    # 예: 인스타, 블로그, 숏폼 (선택)
    product: str | None = Field(default=None, max_length=100)   # 내 상품/서비스 (선택) — 롱테일 키워드·콘텐츠를 여기에 맞춤


@app.post("/api/content-plan")
def content_plan(req: ContentPlanRequest):
    """업종 데이터 + 인구 맥락으로 SNS 콘텐츠 기획안을 만들어 돌려준다."""
    try:
        stats = get_statistics()
        if "message" in stats:
            raise HTTPException(status_code=400, detail="데이터가 없어 기획안을 만들 수 없어요")

        ind = req.industry.strip()
        monthly = stats["monthly"]
        matched = next((k for k in monthly if ind in k or k in ind), None)
        if not matched:
            raise HTTPException(
                status_code=404,
                detail=f"'{ind}' 업종을 찾을 수 없어요. (가능: {', '.join(monthly.keys())})",
            )
        ind = matched
        months = monthly[ind]                       # [{month, avg}, ...]
        peak = max(months, key=lambda m: m["avg"])  # 성수기
        low = min(months, key=lambda m: m["avg"])   # 비수기
        overall_avg = round(sum(m["avg"] for m in months) / len(months), 1)
        std = stats["변동성_표준편차"].get(ind)
        gap = stats["업종간_평균격차"]
        top = stats["최고관심_업종"]

        pop = build_population_summary()
        pop_text = population_summary_to_text(pop) if pop else "- (인구 데이터 없음)"

        facts = (
            f"- 업종: {ind}\n"
            f"- 평균 검색관심도: {overall_avg} (전체 최고관심 업종: {top}, 업종간 평균격차: {gap})\n"
            f"- 성수기(가장 높은 달): {peak['month']} ({peak['avg']}) / 비수기(가장 낮은 달): {low['month']} ({low['avg']})\n"
            f"- 변동성(표준편차): {std} (클수록 시즌 영향이 큼)\n"
        )

        user_ask = f"'{ind}' 업종"
        product = (req.product or "").strip()
        prod_text = f"[내 상품/서비스]\n{product}\n\n" if product else "[내 상품/서비스]\n(입력 없음 — 이 업종의 대표 상품 기준으로 작성)\n\n"
        if req.season:
            user_ask += f", 시즌/테마: {req.season}"
        if req.channel:
            user_ask += f", 채널: {req.channel}"

        system_prompt = (
            "당신은 경남 창원 지역 소상공인을 돕는 SNS 콘텐츠·마케팅 기획 전문가입니다. "
            "아래 '네이버 검색 관심도 데이터'와 '창원 인구 추이'를 근거로, 바로 실행 가능한 "
            "콘텐츠 기획안을 제안하되, 각 콘텐츠의 실제 게시 본문(초안)과 구체적 발행 시점까지 작성하세요. 검색 관심도는 매출이 아니라 관심의 흐름이며, 인구와의 "
            "연결은 '참고' 수준으로만 조심스럽게 쓰세요. 한국어 존댓말로, 아래 형식을 지켜 "
            "간결하고 구체적으로 작성하세요.\n\n"
            "[출력 형식]\n"
            "1) 한줄 진단: 이 업종 관심도 흐름을 한 문장으로\n"
            "2) 추천 콘텐츠 3개 — 각 콘텐츠마다 아래를 모두 작성:\n"
            "   · 제목:\n"
            "   · 본문 초안: 실제 게시물에 바로 올릴 수 있는 2~4문장 글(채널 톤에 맞게, 이모지 1~2개 OK)\n"
            "   · 포맷: 릴스·카드뉴스·블로그 등\n"
            "   · 추천 발행 시점: 성수기 월을 반영한 시기 + 추천 요일·시간대(이유 한 줄)\n"
            "   · 해시태그: 3~5개\n"
            "3) 발행 타이밍 요약: 이 업종은 언제(월·요일·시간대) 올리는 게 유리한지 2~3줄\n"
            "4) 창원 맥락 한마디: 인구 흐름을 고려한 조언 1줄\n"
            "5) 롱테일 키워드 후보 6개: '내 상품/서비스'가 주어지면 그것과 직접 관련된 검색어로, 없으면 이 업종의 대표 상품 기준으로 만드세요. "
            "'지역(창원 동네명 가능)+상품+상황·목적'처럼 3어절 이상의 구체적인 검색어여야 하고, 홍보 콘텐츠 제목·본문에 그대로 쓸 수 있어야 합니다. "
            "각 키워드에 [정보형/비교형/방문형] 중 검색 의도를 붙이세요. 검색량·광고 단가·경쟁 강도 수치는 보유 데이터에 없으므로 절대 지어내지 말고, "
            "'경쟁이 상대적으로 낮을 가능성이 있는 후보'라고만 표현하세요. 마지막 줄에 "
            "'※ 실제 검색량·광고 단가는 네이버 검색광고 키워드 도구 등으로 확인 후 선택하세요'를 덧붙이세요.\n"
            "6) 리뷰 확보 아이디어 3개: 실제 손님이 자발적으로 정직한 후기를 남기도록 돕는 방법(예: 결제·수령 시 QR 안내, 방문 후 감사 메시지, "
            "후기 작성에 대한 소소한 감사 혜택 등)을 각각 '실행 방법 + 손님께 보낼 문구 한 줄'로 제시하세요.\n"
            "[리뷰 안전 규칙] 맞구매(서로 상품을 사주고 리뷰 쓰기), 가짜·대행 리뷰, 긍정 후기만 요구하는 방식, 경쟁업체 비방은 절대 추천하지 마세요. "
            "6) 끝에 '맞구매·가짜 리뷰는 플랫폼 정책 위반이며 노출 불이익·처벌 위험이 있어요' 한 줄을 넣고, 혜택을 제공하는 경우 "
            "협찬·대가 제공 사실을 후기에 표시하도록 안내하세요.\n"
            "※ 요일·시간대는 보유 데이터가 월 단위라서 일반적인 SNS 운영 관행을 참고로 제시하는 것이며, 단정하지 말고 '추천' 톤으로 쓰세요.\n"
        )
        user_prompt = (
            f"[검색 관심도 데이터]\n{facts}\n"
            f"[창원 인구 요약]\n{pop_text}\n\n"
            f"{prod_text}"
            f"위 데이터를 바탕으로 {user_ask} 에 맞는 SNS 콘텐츠 기획안을 만들어 주세요."
        )

        client = OpenAI(
            api_key=os.getenv("CODYSSEY_API_KEY"),
            base_url="https://copa.codyssey.kr/v1",
        )
        completion = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **token_limit(),
        )
        plan = completion.choices[0].message.content

        return {
            "industry": ind,
            "season": req.season,
            "channel": req.channel,
            "product": product,
            "data_used": {
                "평균관심도": overall_avg,
                "성수기": peak,
                "비수기": low,
                "변동성": std,
                "최고관심업종": top,
                "업종간격차": gap,
            },
            "plan": plan,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
