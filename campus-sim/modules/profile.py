# profile 모듈 — 이번 학기 내 상황을 입력받습니다. (F01 / 문제1)
# 학번 · 실명 · 가구 소득은 받지 않습니다.

PROFILE_FIELDS = ["term", "current_gpa", "course_credits", "weekly_free_hours"]


def validate(term, current_gpa, course_credits, weekly_free_hours) -> None:
    if not term:
        raise ValueError("학기를 입력해야 합니다. 예: 2026-2")
    if current_gpa is None or not 0 <= current_gpa <= 4.5:
        raise ValueError("현재 학점은 0.0에서 4.5 사이로 입력해야 합니다.")
    if course_credits is None or not 1 <= course_credits <= 30:
        raise ValueError("수강 학점은 1에서 30 사이로 입력해야 합니다.")
    if weekly_free_hours is None or not 1 <= weekly_free_hours <= 168:
        raise ValueError("주간 자유 시간은 1에서 168 사이로 입력해야 합니다.")


def build_profile(term, current_gpa, course_credits, weekly_free_hours) -> dict:
    term = (term or "").strip()
    validate(term, current_gpa, course_credits, weekly_free_hours)
    return {
        "term": term,
        "current_gpa": float(current_gpa),
        "course_credits": int(course_credits),
        "weekly_free_hours": float(weekly_free_hours),
    }
