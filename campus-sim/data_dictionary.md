# 데이터 사전 (9주차 목적 정의서 · 10주차 확정 모듈 구성표 기준)
저장 형태: data/simulation_log.csv 한 파일 (utf-8-sig). 한 줄 = 한 학기 · 한 선택지, 항목 10개. 칸을 늘리지 않습니다.

| 구분 | 항목명 | 설명 | 예시 | 쓰는 모듈 |
|---|---|---|---|---|
| 프로필 | term | 학기 | 2026-2 | scenario (학기 초) |
| 프로필 | current_gpa | 현재 학점 (0.0~4.5) | 3.8 | scenario |
| 프로필 | course_credits | 이번 학기 수강 학점 | 18 | scenario |
| 프로필 | weekly_free_hours | 수업 외 주간 자유 시간 | 25 | scenario |
| 시나리오 | scenario_option | 선택지 | 인턴 병행 | scenario |
| 시나리오 | scenario_hours | 주간 투입 시간 | 15 | scenario |
| 시나리오 | scenario_condition | 세부 조건 (글) | 주 3일 근무 | scenario |
| 실제 결과 | actual_gpa | 실제 학점 | 3.5 | feedback (학기 말) |
| 실제 결과 | satisfaction | 만족도 1~5 | 4 | feedback |
| 실제 결과 | user_review | 자유 평가 (글) | 과제 시간이 부족했다 | feedback |

- 학기 초에는 실제 결과 3칸이 빈칸이고, 학기 말에 실제로 고른 선택지의 줄만 채웁니다.
- 수집하지 않는 것: 학번 · 실명 · 가구 소득.
- 예상 학점과 AI 보정값은 저장하지 않습니다. 예측 오차는 저장된 입력으로 계산식을 다시 돌려 구합니다.
