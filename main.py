"""나만의 AI 비서 — FastAPI 앱 시작점.

여기서는 앱을 만들고 설정(CORS·오류 안내)과 API 경로(routers)만 붙여요.
  routers/   : API 경로 (data · population · chat · agent · conversations · content_plan)
  services/  : 계산·외부 연동 (summary · population · llm · agent_tools)
  config.py  : 환경변수 설정 / schemas.py : 요청 모델 / errors.py : 한글 오류 안내
실행: uvicorn main:app --reload
"""
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_ORIGINS
from errors import validation_error_handler
from routers import agent, chat, content_plan, conversations, data, population

app = FastAPI(title="나만의 AI 비서")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(RequestValidationError, validation_error_handler)


@app.get("/")
def read_root():
    return {"message": "AI 비서 서버가 잘 작동하고 있어요!"}


app.include_router(data.router)
app.include_router(population.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(agent.router)
app.include_router(content_plan.router)
