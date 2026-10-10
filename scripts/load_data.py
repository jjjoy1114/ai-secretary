import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""네이버 데이터랩 CSV(1,098행)를 Firestore 'data' 컬렉션에 넣는 코드."""
import csv
from firebase_config import db

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "datalab_data.csv")   # 같은 폴더 안의 데이터 파일

count = 0
batch = db.batch()      # 여러 개를 한 번에 저장하는 '상자'
batch_size = 0

with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)   # 첫 줄(date,value,memo)을 이름표로 사용
    for row in reader:
        date = row["date"].strip()
        memo = row["memo"].strip()
        if not row["value"].strip():
            continue             # 값이 비어있는 줄은 건너뜀
        value = float(row["value"])

        # 업종+날짜로 고유 ID → 다시 실행해도 중복 없이 덮어써짐
        doc_id = f"{memo}_{date}".replace("/", "_")   # 업종명 속 / 는 _ 로 (경로 오류 방지)
        ref = db.collection("data").document(doc_id)
        batch.set(ref, {"date": date, "value": value, "memo": memo})

        batch_size += 1
        count += 1
        if batch_size == 500:    # Firestore는 한 상자에 최대 500개
            batch.commit()
            print(f"  ... {count}개 저장 중")
            batch = db.batch()
            batch_size = 0

if batch_size > 0:
    batch.commit()

print("=========================================")
print(f"✅ 완료! Firestore 'data' 컬렉션에 총 {count}개 데이터를 저장했어요.")
print("=========================================")
