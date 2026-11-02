# 🤖 나만의 AI 비서 — 창원 업종 관심도·인구 분석 비서

경남 **창원** 지역 소상공인을 위한 **데이터 기반 AI 비서** 웹 서비스입니다.
네이버 데이터랩 검색관심도(3업종)와 KOSIS 창원시 인구 데이터를 요약·분석하고,
그 요약을 **GPT에 주입**해 "왜 그런지"까지 대화로 설명하며, SNS **콘텐츠 기획안**까지 제안합니다.

> AI 응용 학습(M1-2) 개인 과제 — "AI Agent 개발: 나만의 AI 비서"

---

## 🔗 배포 주소

| 구분 | 주소 |
|---|---|
| 프론트엔드 (Vercel) | https://ai-secretary-omega-eight.vercel.app |
| 백엔드 API (Render) | https://ai-secretary-07fk.onrender.com |
| API 문서 (Swagger) | https://ai-secretary-07fk.onrender.com/docs |

> ⏱️ **콜드스타트 안내** — 백엔드는 Render 무료 요금제라 15분 이상 미사용 시 잠듭니다.
> 첫 접속 시 깨어나는 데 **30초~1분** 걸릴 수 있어요(정상). 두 번째부터는 빠릅니다.

---

## 📊 데이터

- **검색관심도(시계열)** : 네이버 데이터랩 — 창원 3업종(**카페 · 미용/뷰티 · 미용의료**) 상대지수(0~100), 총 **1,098행**(업종별 366일)
- **인구(보강 데이터)** : KOSIS 국가통계포털 — 창원시 월별 주민등록인구
- **데이터 구조** : `date`(날짜) / `value`(지수) / `memo`(업종)

---

## 🛠️ 기술 스택

| 영역 | 사용 기술 |
|---|---|
| 백엔드 | FastAPI (Python) |
| 프론트엔드 | HTML / CSS / JavaScript (바닐라) |
| 데이터베이스 | Firebase Firestore |
| AI | OpenAI GPT API (코디세이 게이트웨이, `gpt-5-mini`) |
| 외부 데이터 | 네이버 데이터랩 · KOSIS OpenAPI |
| 시각화 / 내보내기 | Chart.js · SheetJS |
| 배포 | 백엔드 **Render** · 프론트 **Vercel** |
| 멀티채널 | **MCP (Model Context Protocol) Server** |

---

## ✨ 주요 기능

- 데이터 **CRUD** (추가 / 조회 / 수정 / 삭제)
- 업종별 **요약**(`/api/data/summary`) 및 상세 **통계**(`/api/data/statistics`)
- 창원 **인구 연동** 및 요약(`/api/population*`)
- **AI 대화** — 데이터 요약을 GPT 시스템 프롬프트에 주입해 답변(`/api/chat`)
- 대화 기록 **저장 / 조회**(`/api/conversations`)
- **콘텐츠 추천** — 업종 데이터 기반 SNS 콘텐츠 기획안 생성(`/api/content-plan`)

---

## 🏆 보너스 과제

### A. AI 도구 호출(Function Calling) + 멀티채널

**A-1. 도구 호출** — `/api/agent`
GPT가 질문을 보고 **필요한 내부 기능(API)을 '도구'로 스스로 호출**해 실제 데이터를 확인한 뒤 답합니다.

| 도구 | 호출하는 경우(근거) |
|---|---|
| `get_search_summary` | "요약 / 분위기 / 전반적 흐름"을 물을 때 |
| `get_statistics` | "변동성 / 월별 추이 / 업종 간 격차"가 필요할 때 |
| `get_population_summary` | "창원 인구 / 손님(모집단) 변화" 맥락이 필요할 때 |

**A-2. 멀티채널 (MCP)**
동일 기능을 **MCP Server(`mcp_server.py`)**로도 노출해, 외부 클라이언트인 **Claude(Claude Code)**에서 호출합니다.
MCP 도구: `get_search_summary` · `get_statistics` · `get_population_summary` · `make_content_plan`

#### 🔁 호출 흐름 (어떤 근거로 어떤 도구를 호출하는가)

```
[사용자 질문]  예) "창원 카페 분위기 요약해줘"
      │
      ▼
[Claude(외부 채널) / GPT 가 의도 파악 → 도구 선택]
   · 요약/분위기        → get_search_summary
   · 변동성/월별 흐름    → get_statistics
   · 인구/손님 변화      → get_population_summary
   · 콘텐츠/홍보 아이디어 → make_content_plan
      │
      ▼
[MCP Server(mcp_server.py)] ──HTTP──▶ [백엔드(Render)] ──▶ [Firestore 데이터]
      │
      ▼
[도구 결과(JSON)를 받아 자연어로 요약·설명]
```

- MCP 서버는 GPT 키를 직접 쓰지 않고, **이미 배포된 백엔드(Render)를 호출**합니다. (키 관리가 늘지 않음)
- 검증: `claude mcp list` → `ai-secretary ✓ Connected`, Claude Code에서 `Called ai-secretary` 호출 확인(스크린샷 첨부).

### B. 인사이트·UX 고도화

- 추가 지표 제공 — `/api/data/statistics` (변동성·업종 간 평균 격차·최고 관심 업종)
- 프론트 **추세 그래프**(Chart.js, 업종별 월별 평균 3선)
- 데이터 **내보내기** — CSV / JSON / Excel
- **다크 모드** 토글

---

## 💻 로컬 실행 방법

```bash
# 1) 가상환경 활성화
.\venv\Scripts\activate          # Windows
# source venv/bin/activate       # mac / Linux

# 2) 패키지 설치
pip install -r requirements.txt

# 3) 백엔드 실행
uvicorn main:app --reload
#   → http://127.0.0.1:8000/docs (Swagger)

# 4) 프론트엔드
#   index.html 을 브라우저로 열기
```

### MCP 서버(멀티채널) 사용

```bash
# MCP 패키지 설치 (v1 계열)
pip install "mcp<2" requests

# Claude Code 에 서버 등록
claude mcp add --transport stdio --scope user ai-secretary -- "<venv python 경로>" "<mcp_server.py 경로>"

# 연결 확인
claude mcp list        # ai-secretary ✓ Connected
```

---

## 🔑 환경변수 (`.env`)

| 변수 | 설명 |
|---|---|
| `CODYSSEY_API_KEY` | GPT 호출 키 (코디세이 게이트웨이) |
| `KOSIS_API_KEY` | KOSIS 인구 API 키 |
| `FIREBASE_KEY_PATH` | (로컬) Firebase 서비스계정 키 파일 경로 |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | (배포) Firebase 서비스계정 키 JSON 전체 내용 |

> 🔒 API 키·서비스계정 키 파일은 `.gitignore`로 GitHub에 올라가지 않습니다.
> 코드에 직접 노출하지 않고 **환경변수로만** 관리합니다.

---

## 📁 폴더 구조

```
ai-secretary/
├─ main.py                # FastAPI 백엔드 (API 전체)
├─ firebase_config.py     # Firestore 연결
├─ kosis_client.py        # KOSIS 인구 API 클라이언트
├─ mcp_server.py          # MCP 서버 (멀티채널 — Claude 연동)
├─ index.html             # 프론트엔드 (대시보드)
├─ requirements.txt
├─ data/                  # 원본 CSV
├─ scripts/               # 데이터 적재·테스트 스크립트
└─ backups/               # 작업 백업본
```

---

## 🖼️ 제출용 스크린샷 (체크리스트)

- [ ] 배포 URL 접속 (프론트 / 백엔드 `/docs`)
- [ ] 데이터 CRUD 동작
- [ ] AI 대화 (`/api/chat`)
- [ ] 보너스 A — `/api/agent` 도구 호출
- [ ] 보너스 A — MCP `claude mcp list ✓ Connected` + `Called ai-secretary` 호출
- [ ] 보너스 B — 추세 그래프 · 내보내기 · 다크모드
