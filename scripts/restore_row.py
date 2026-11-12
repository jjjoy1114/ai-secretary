import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""미용/뷰티 2025-09-12 한 행만 data 컬렉션에 복구합니다.
기본은 '미리보기'(저장 안 함). 확인 후 --apply 를 붙여 실행하면 저장합니다."""
import csv
from firebase_config import db

MEMO, DATE = "미용/뷰티", "2025-09-12"
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

row = None
with open(os.path.join(root, "data", "datalab_data.csv"), encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        if r["memo"].strip() == MEMO and r["date"].strip() == DATE:
            row = r
if row is None:
    raise SystemExit("원본 CSV에서 해당 행을 찾지 못했어요.")

doc_id = f"{MEMO}_{DATE}".replace("/", "_")
data = {"date": DATE, "value": float(row["value"]), "memo": MEMO}
ref = db.collection("data").document(doc_id)
exists = ref.get().exists

print("=========================================")
print("문서 ID  :", doc_id)
print("저장 내용:", data)
print("이미 있음:", exists)
if "--apply" not in sys.argv:
    print("[미리보기] 아직 저장하지 않았어요. 맞으면 --apply 를 붙여 다시 실행하세요.")
elif exists:
    print("이미 있는 행이라 저장하지 않았어요.")
else:
    ref.set(data)
    print("[저장 완료] 1행을 복구했어요.")
print("=========================================")
