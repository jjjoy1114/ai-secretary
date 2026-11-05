"""AI 에이전트 API — /api/agent (GPT가 필요한 도구를 스스로 골라 호출)."""
from fastapi import APIRouter, HTTPException

from config import token_limit
from schemas import ChatRequest
from services.agent_tools import AGENT_TOOLS, run_agent_tool
from services.llm import MODEL, get_client, load_history, save_turn

router = APIRouter()


# ============================================================
# 보너스 과제 A — AI 도구 호출 (Function Calling)
#   기존 /api/chat 은 요약을 '통째로' 시스템 프롬프트에 주입한다.
#   여기 /api/agent 는 GPT가 질문을 보고 '필요한 도구(함수)'를
#   스스로 골라 호출한 뒤, 그 결과로 답한다. → 진짜 '에이전트(비서)'
# ============================================================
@router.post("/api/agent")
def agent(req: ChatRequest):
    """GPT가 필요한 도구를 스스로 호출해서 답하는 '에이전트' 채팅."""
    try:
        system_prompt = (
            "당신은 경남 창원 지역 소상공인을 돕는 친절한 데이터 분석 비서입니다. "
            "답하기 전에, 필요한 수치가 있으면 반드시 제공된 도구(함수)를 호출해 "
            "실제 데이터를 확인한 뒤 답하세요. 추측으로 숫자를 지어내지 말고, "
            "한국어 존댓말로 쉽고 구체적으로 답하세요."
        )

        history = load_history(req.conversation_id)
        messages = [{"role": "system", "content": system_prompt}]
        messages += history
        messages.append({"role": "user", "content": req.message})

        client = get_client()
        tools_used = []   # 어떤 도구를 불렀는지 기록 (보고서 증거용)
        reply = ""

        # GPT <-> 도구 호출을 최대 5번까지 주고받는다
        for _ in range(5):
            completion = client.chat.completions.create(
                model=MODEL,
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
        conv_id = save_turn(req.conversation_id, history, req.message, reply)
        return {"conversation_id": conv_id, "reply": reply, "tools_used": tools_used}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
