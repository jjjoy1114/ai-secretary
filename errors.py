"""입력 검사에 걸렸을 때 영어 대신 알기 쉬운 한글로 알려주기."""
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from config import logger

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
