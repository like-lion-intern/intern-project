import csv
import json
import os


def load_data(date, base_path="."):
    """
    Loads features.json and semantic_chunks.json for a given date.
    """
    features_path = os.path.join(base_path, "features", f"{date}.json")
    chunks_path = os.path.join(base_path, "semantic_chunks", f"{date}.json")

    if not os.path.exists(features_path):
        raise FileNotFoundError(f"Features file not found: {features_path}")
    if not os.path.exists(chunks_path):
        raise FileNotFoundError(f"Chunks file not found: {chunks_path}")

    with open(features_path, "r", encoding="utf-8") as f:
        features_data = json.load(f)

    with open(chunks_path, "r", encoding="utf-8") as f:
        chunks_data = json.load(f)

    return features_data, chunks_data


def load_curriculum(date: str, base_path: str = "..") -> dict:
    """
    강의_메타데이터.csv에서 해당 날짜의 커리큘럼 정보를 로드.
    같은 날짜에 content가 여러 개인 경우 모두 합쳐서 반환.

    반환 형태:
    {
        "date": "2026-02-05",
        "course_name": "백엔드 부트캠프 21기: Java",
        "subject": "Front-End Programming",
        "contents": ["JavaScript 기본 문법"],   # 중복 제거한 unique content 목록
        "instructor": "김영아",
    }
    없으면 None 반환.
    """
    csv_path = os.path.join(base_path, "강의 메타데이터.csv")
    if not os.path.exists(csv_path):
        return None

    matched_rows = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("date", "").strip() == date:
                matched_rows.append(row)

    if not matched_rows:
        return None

    # content 중복 제거 (순서 유지)
    seen = set()
    unique_contents = []
    for row in matched_rows:
        c = row.get("content", "").strip()
        if c and c not in seen:
            seen.add(c)
            unique_contents.append(c)

    first = matched_rows[0]
    return {
        "date": date,
        "course_name": first.get("course_name", "").strip(),
        "subject": first.get("subject", "").strip(),
        "contents": unique_contents,
        "instructor": first.get("instructor", "").strip(),
    }