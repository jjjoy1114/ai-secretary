import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""data 컬렉션에서 빠진 날짜 찾기 — 읽기만 합니다(저장·삭제 없음).
원본 CSV(data/datalab_data.csv)와 Firestore data 컬렉션을 비교해서 없는 행을 알려 줍니다."""
import csv
from firebase_config import db

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = list(csv.DictReader(open(os.path.join(root, "data", "datalab_data.csv"), encoding="utf-8-sig")))
csv_keys = {(r["memo"], r["date"]): r["value"] for r in rows}

fs_keys = set()
for doc in db.collection("data").stream():
    d = doc.to_dict()
    fs_keys.add((d.get("memo"), d.get("date")))

print("=========================================")
print("원본 CSV:", len(csv_keys), "행 / Firestore data:", len(fs_keys), "행")
missing = sorted(set(csv_keys) - fs_keys)
extra = sorted(fs_keys - set(csv_keys))
print("CSV에는 있는데 Firestore에 없는 행(", len(missing), "개):")
for m in missing:
    print("  ", m[0], m[1], "value =", csv_keys[m])
print("Firestore에만 있는 행(", len(extra), "개):")
for e in extra:
    print("  ", e)
print("=========================================")
