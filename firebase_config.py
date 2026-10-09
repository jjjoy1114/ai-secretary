"""Firebase(Firestore) 연결 설정 — 창고 문을 여는 코드."""
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

load_dotenv()  # .env 파일에 적어둔 값을 불러옵니다

# 앱이 아직 연결 안 됐을 때만 연결 (중복 연결 방지)
if not firebase_admin._apps:
    key_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")  # 배포(Render)용
    if key_json:
        cred = credentials.Certificate(json.loads(key_json))
    else:  # 로컬용: 열쇠 파일 경로로 연결
        key_path = os.getenv("FIREBASE_KEY_PATH", "serviceAccountKey.json")
        cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred)

# 다른 파일에서 'db'를 가져다 쓰면 창고를 쓸 수 있어요
db = firestore.client()
