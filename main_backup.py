from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

# 기본 주소("/") — 서버가 잘 살아있는지 확인하는 창구
@app.get("/")
def read_root():
    return {"message": "AI 비서 서버가 잘 작동하고 있어요!"}
