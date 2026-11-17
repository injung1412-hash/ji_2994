# feedback 모듈 — 학기 말 실제 결과를 고른 선택지의 CSV 줄에 채우고, (F07)
# 저장된 입력으로 계산식을 다시 돌려 예측과의 차이를 보여 준 뒤 (F11)
# 다음 예측에 지난 학기 기록으로 넘깁니다. (F08 / 문제3)
from modules.scenario import LOG_PATH, read_log, write_log
from modules.simulation import base_gpa

REVIEW_NOTICE = "다른 사람 이름이나 연락처는 적지 마세요."


def is_filled(row: dict) -> bool:
    return row["actual_gpa"] != ""


def open_rows(path=LOG_PATH) -> list:
    """실제 결과가 아직 비어 있는 줄: [(줄 번호, 줄), ...]"""
    return [(index, row) for index, row in enumerate(read_log(path)) if not is_filled(row)]


def validate(actual_gpa, satisfaction, user_review) -> None:
    if actual_gpa is None or not 0 <= actual_gpa <= 4.5:
        raise ValueError("실제 학점은 0.0에서 4.5 사이로 입력해야 합니다.")
    if satisfaction not in (1, 2, 3, 4, 5):
        raise ValueError("만족도는 1에서 5 사이로 골라야 합니다.")
    if not user_review:
        raise ValueError("자유 평가를 한 줄 이상 적어야 10개 항목이 빠짐없이 남습니다.")


def predicted(row: dict) -> float:
    """저장된 입력으로 계산식을 다시 돌린 예상 학점"""
    value, _ = base_gpa(
        row["current_gpa"], row["course_credits"], row["weekly_free_hours"], row["scenario_hours"], row["scenario_option"]
    )
    return value


def with_error(row: dict) -> dict:
    value = predicted(row)
    return {**row, "predicted_gpa": value, "error": round(float(row["actual_gpa"]) - value, 2)}


def record_result(index: int, actual_gpa, satisfaction, user_review, path=LOG_PATH) -> dict:
    user_review = (user_review or "").strip()
    validate(actual_gpa, satisfaction, user_review)
    rows = read_log(path)
    if not 0 <= index < len(rows):
        raise ValueError("고른 선택지를 기록에서 찾지 못했습니다.")
    if is_filled(rows[index]):
        raise ValueError("이 선택지는 이미 실제 결과가 기록되어 있습니다.")
    rows[index].update(
        {"actual_gpa": f"{float(actual_gpa):g}", "satisfaction": str(int(satisfaction)), "user_review": user_review}
    )
    write_log(rows, path)
    return with_error(rows[index])


def history(path=LOG_PATH) -> list:
    """실제 결과가 채워진 줄과 예측 오차"""
    return [with_error(row) for row in read_log(path) if is_filled(row)]


def past_records(current_term: str, path=LOG_PATH) -> list:
    """다음 예측에 넘길 지난 학기 기록(이번 학기 기록은 빼고 넘깁니다)"""
    return [row for row in history(path) if row["term"] != current_term]


def mean_abs_error(rows: list):
    if not rows:
        return None
    return round(sum(abs(row["error"]) for row in rows) / len(rows), 2)
