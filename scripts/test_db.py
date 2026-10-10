import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Firestore 연결 테스트 — 창고에 한 줄 저장했다가 다시 읽어봅니다."""
from datetime import datetime
from firebase_config import db

doc_ref = db.collection("_healthcheck").document("ping")
doc_ref.set({"message": "연결 성공!", "time": datetime.now().isoformat()})

saved = doc_ref.get().to_dict()
print("=========================================")
print("✅ Firestore 연결 성공! 저장된 값:", saved)
print("=========================================")
