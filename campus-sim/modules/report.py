# report 모듈 — 어떤 선택이 어떤 점에서 나은지 짧게 정리합니다. (F10 / 문제1)
# 하나를 정답으로 단정하지 않으며, 결정은 사용자가 합니다.

NOTICE = "추정치이며 결과를 보장하지 않습니다."
DECISION = "이 보고서는 비교 근거일 뿐이며, 결정은 내가 합니다."


def names(rows: list) -> str:
    return ", ".join(row["scenario_option"] for row in rows)


def best_rows(rows: list, key: str) -> list:
    top = max(row[key] for row in rows)
    return [row for row in rows if row[key] == top]


def option_line(row: dict) -> str:
    ai = f"AI 보정 {row['adjust']:+.2f}" if row["ai_used"] else "AI 보정 없음"
    line = (
        f"- **{row['scenario_option']}** (주 {row['scenario_hours']:g}시간): "
        f"남는 자유 시간 {row['free_left']:g}시간, 예상 학점 {row['expected_gpa']:.2f} "
        f"(보정 전 {row['base_gpa']:.2f}, {ai})"
    )
    if row.get("study"):
        line += " — 📚 공부 시간으로 계산"
    if row["short"]:
        line += " — ⚠️ 시간 부족"
    return line


def make_report(table: dict) -> str:
    rows = table["rows"]
    parts = [f"선택지 {len(rows)}개를 같은 기준(남는 자유 시간 · 예상 학점)으로 비교했습니다."]
    parts.append("\n".join(option_line(row) for row in rows))

    if len(rows) >= 2:
        gpa_rows = best_rows(rows, "expected_gpa")
        time_rows = best_rows(rows, "free_left")
        parts.append(
            f"- 예상 학점 면에서는 **{names(gpa_rows)}**이(가) {gpa_rows[0]['expected_gpa']:.2f}로 가장 높습니다.\n"
            f"- 남는 자유 시간 면에서는 **{names(time_rows)}**이(가) {time_rows[0]['free_left']:g}시간으로 가장 많습니다."
        )

    if table["warnings"]:
        parts.append("시간이 모자라는 선택지가 있습니다.\n\n" + "\n".join(f"- {w}" for w in table["warnings"]))
    else:
        parts.append("모든 선택지가 주간 자유 시간 안에 들어갑니다.")

    parts.append(f"{NOTICE} {DECISION}")
    return "\n\n".join(parts)
