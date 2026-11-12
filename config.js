// 프론트엔드 설정 — 배포 주소가 바뀌면 이 파일만 고치면 돼요 (index.html은 건드리지 않아도 돼요).
// (비밀 키가 아니라 공개돼도 괜찮은 '서버 주소'만 적어요)
window.APP_CONFIG = {
  // 배포된 백엔드(Render) 주소
  API_URL: "https://ai-secretary-07fk.onrender.com",
  // 내 컴퓨터에서 'localhost'로 화면을 열었을 때 쓸 로컬 서버 주소 (uvicorn main:app --reload)
  LOCAL_API_URL: "http://localhost:8000",
};
