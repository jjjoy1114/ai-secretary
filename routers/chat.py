"""AI 채팅 API — /api/chat (요약을 GPT에 주입해서 대화 + 자동 저장)."""
from fastapi import APIRouter, HTTPException

from config import token_limit
from schemas import ChatRequest
from services.llm import MODEL, get_client, load_history, save_turn
from services.population import build_population_summary, population_summary_to_text
from services.summary import build_summary, summary_to_text

router = APIRouter()


# ============================================================
# AI 채팅 API — 요약을 GPT에 주입해서 대화 + 자동 저장
#   * 문제 원인을 화면에 그대로 보여주도록 try/except 로 감쌈
# ============================================================
@router.post("/api/chat")
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

        history = load_history(req.conversation_id)
        messages = [{"role": "system", "content": system_prompt}]
        messages += history
        messages.append({"role": "user", "content": req.message})

        completion = get_client().chat.completions.create(
            model=MODEL,
            messages=messages,
            **token_limit(),
        )
        reply = completion.choices[0].message.content

        conv_id = save_turn(req.conversation_id, history, req.message, reply)
        return {"conversation_id": conv_id, "reply": reply}

    except HTTPException:
        raise
    except Exception as e:
        # 진짜 원인을 화면(Response)에 그대로 보여줌
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
