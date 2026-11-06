"""설정값 — 환경변수로 바꿀 수 있고, 적지 않으면 기본값을 써요.

  ALLOWED_ORIGINS    : CORS 허용 주소(쉼표로 여러 개). 기본 "*" = 모두 허용(데모·채점용)
  SUMMARY_RECENT_DAYS: 추세 비교에 쓰는 '최근 N일' (기본 30 → 최근30일 vs 그 앞 30일)
  MAX_TOKENS         : GPT 답변 길이 상한(비용 보호). 기본 6000, 0 = 제한 안 함
                       (gpt-5-mini는 "생각"에도 토큰을 써서 너무 작으면 빈 답변이 와요)
"""
import os
import logging

from dotenv import load_dotenv

load_dotenv()  # .env 파일 값을 먼저 불러와야 아래 설정에 반영돼요

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ai-secretary")   # 서버 기록(Render의 Logs 화면에서 볼 수 있어요)


def _env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "*").split(",") if o.strip()] or ["*"]
SUMMARY_RECENT_DAYS = max(1, _env_int("SUMMARY_RECENT_DAYS", 30))
MAX_TOKENS = _env_int("MAX_TOKENS", 6000)


def token_limit():
    """MAX_TOKENS가 0보다 클 때 GPT 호출에 길이 상한을 붙여요. (0으로 두면 제한 없음)"""
    return {"max_completion_tokens": MAX_TOKENS} if MAX_TOKENS > 0 else {}
