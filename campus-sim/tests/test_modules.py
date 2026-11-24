# 모듈 6개 확인 (10주차 완성 확인 방법 기준) — 실행: python3 -m unittest discover -s tests
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import compare, counsel, feedback, profile, report, scenario, simulation

PROFILE = profile.build_profile("2026-2", 3.8, 18, 25)


def plans(*hours):
    names = ["인턴 병행", "학점 집중", "동아리 확대"]
    return scenario.build_scenarios(
        [{"scenario_option": names[i], "scenario_hours": h, "scenario_condition": f"조건 {i}"} for i, h in enumerate(hours)]
    )


def no_ai(_):
    raise ValueError("AI 연결 끊김")


class ProfileScenarioTest(unittest.TestCase):
    def test_profile_four_items(self):
        self.assertEqual(list(PROFILE), profile.PROFILE_FIELDS)

    def test_profile_rejects_bad_values(self):
        for args in [("", 3.8, 18, 25), ("2026-2", 4.6, 18, 25), ("2026-2", 3.8, 0, 25), ("2026-2", 3.8, 18, 0)]:
            with self.assertRaises(ValueError):
                profile.build_profile(*args)

    def test_scenarios_validation(self):
        with self.assertRaises(ValueError):
            scenario.build_scenarios([])
        with self.assertRaises(ValueError):
            scenario.build_scenarios([{"scenario_option": "A", "scenario_hours": 1}] * 2)
        with self.assertRaises(ValueError):
            scenario.build_scenarios([{"scenario_option": "", "scenario_hours": 1}])

    def test_save_plan_writes_ten_items_and_updates_same_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "simulation_log.csv"
            scenario.save_plan(PROFILE, plans(15, 5), path)
            scenario.save_plan(PROFILE, plans(10, 5), path)
            rows = scenario.read_log(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(list(rows[0]), scenario.LOG_FIELDS)
            self.assertEqual(len(scenario.LOG_FIELDS), 10)
            self.assertEqual(rows[0]["scenario_hours"], "10")
            self.assertEqual(rows[0]["actual_gpa"], "")
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))


class ActivityTest(unittest.TestCase):
    def test_build_with_activities_encodes_name_and_total(self):
        built = scenario.build_scenarios(
            [{"activities": [{"name": "인턴 병행", "hours": 15}, {"name": "공부", "hours": 5}], "scenario_condition": "주 3일"}]
        )[0]
        self.assertEqual(built["scenario_option"], "인턴 병행(15) + 공부(5)")
        self.assertEqual(built["scenario_hours"], 20)
        self.assertEqual(scenario.parse_activities(built["scenario_option"], 20), [("인턴 병행", 15), ("공부", 5)])

    def test_single_activity_saved_as_before(self):
        built = scenario.build_scenarios([{"activities": [{"name": "인턴 병행", "hours": 15}]}])[0]
        self.assertEqual((built["scenario_option"], built["scenario_hours"]), ("인턴 병행", 15))
        self.assertEqual(scenario.parse_activities("인턴 병행", 15), [("인턴 병행", 15)])
        self.assertEqual(scenario.parse_activities("A(3) + B(4)", 9), [("A(3) + B(4)", 9)])   # 합계가 다르면 조합으로 보지 않음

    def test_activity_validation(self):
        bad = [
            [{"name": "", "hours": 5}, {"name": "공부", "hours": 5}],
            [{"name": "인턴+알바", "hours": 5}, {"name": "공부", "hours": 5}],
            [{"name": "공부", "hours": 5}, {"name": "공부", "hours": 3}],
            [{"name": "인턴", "hours": 100}, {"name": "공부", "hours": 100}],
            [{"name": f"활동{i}", "hours": 1} for i in range(6)],
        ]
        for activities in bad:
            with self.assertRaises(ValueError):
                scenario.build_scenarios([{"activities": activities}])

    def test_mixed_gpa_splits_study_and_other(self):
        # 인턴 15(공부 외) + 공부 5: 3.8 + (25 − 15 − 15)×0.02 + 5×0.01 = 3.75
        self.assertEqual(simulation.base_gpa(3.8, 18, 25, 20, "인턴 병행(15) + 공부(5)")[0], 3.75)
        # 공부 시간은 공부 외 시간을 뺀 자유 시간까지만 인정: 인턴 20 + 공부 20 → 공부 5시간만
        self.assertEqual(simulation.base_gpa(3.8, 18, 25, 40, "인턴(20) + 공부(20)")[0], 3.65)
        row = simulation.calculate(PROFILE, {"scenario_option": "인턴 병행(15) + 공부(5)", "scenario_hours": 20})
        self.assertEqual((row["label"], row["study_hours"], row["study"], row["all_study"]), ("인턴 병행 + 공부", 5, True, False))
        self.assertEqual(compare.time_type(row), "혼합 (📚 공부 5시간)")


class SimulationTest(unittest.TestCase):
    def test_formula_examples_from_plan(self):
        # 현재 학점 3.8, 18학점, 자유 시간 25시간: 0시간 4.0, 5시간 3.9, 10시간 3.8, 15시간 3.7
        for hours, expected in [(0, 4.0), (5, 3.9), (10, 3.8), (15, 3.7)]:
            self.assertEqual(simulation.base_gpa(3.8, 18, 25, hours)[0], expected)

    def test_study_option_raises_gpa_with_hours(self):
        # 공부형: 현재 학점 3.8, 18학점, 자유 시간 25시간 → 0시간 4.0, 5시간 4.05, 15시간 4.15
        for hours, expected in [(0, 4.0), (5, 4.05), (15, 4.15)]:
            self.assertEqual(simulation.base_gpa(3.8, 18, 25, hours, "학점 집중")[0], expected)
        # 같은 15시간이라도 공부형은 오르고, 인턴은 내려갑니다
        self.assertGreater(simulation.base_gpa(3.8, 18, 25, 15, "공부")[0], 3.8)
        self.assertLess(simulation.base_gpa(3.8, 18, 25, 15, "인턴 병행")[0], 3.8)
        # 공부 시간은 자유 시간까지만 인정
        self.assertEqual(simulation.base_gpa(3.8, 18, 25, 40, "공부")[0], simulation.base_gpa(3.8, 18, 25, 25, "공부")[0])

    def test_is_study_keywords(self):
        for name in ["공부", "학점 집중", "시험 준비", "스터디 그룹", "복습"]:
            self.assertTrue(simulation.is_study(name))
        for name in ["인턴 병행", "동아리 확대", "아르바이트", ""]:
            self.assertFalse(simulation.is_study(name))

    def test_free_left_and_clamp(self):
        self.assertEqual(simulation.free_left(25, 30), -5)
        self.assertEqual(simulation.base_gpa(4.5, 18, 25, 0)[0], 4.5)
        self.assertEqual(simulation.base_gpa(0.0, 30, 10, 60)[0], 0.0)

    def test_same_input_same_result(self):
        first = simulation.run(PROFILE, plans(15, 5), ask=no_ai)
        second = simulation.run(PROFILE, plans(15, 5), ask=no_ai)
        self.assertEqual(first, second)

    def test_ai_failure_falls_back_to_formula(self):
        result = simulation.run(PROFILE, plans(15), ask=no_ai)
        row = result["rows"][0]
        self.assertFalse(row["ai_used"])
        self.assertEqual(row["expected_gpa"], 3.7)
        self.assertTrue(row["reason"].startswith("AI 보정 없음"))

    def test_ai_adjust_inside_limit_is_applied(self):
        answer = '{"results": [{"scenario_option": "인턴 병행", "adjust": -0.2, "reason": "주 3일 근무"}]}'
        row = simulation.run(PROFILE, plans(15), ask=lambda _: answer)["rows"][0]
        self.assertTrue(row["ai_used"])
        self.assertEqual(row["expected_gpa"], 3.5)
        self.assertEqual(row["base_gpa"], 3.7)

    def test_ai_adjust_outside_limit_is_dropped(self):
        answer = '{"results": [{"scenario_option": "인턴 병행", "adjust": 0.5, "reason": "x"}]}'
        row = simulation.run(PROFILE, plans(15), ask=lambda _: answer)["rows"][0]
        self.assertFalse(row["ai_used"])
        self.assertEqual(row["expected_gpa"], 3.7)

    def test_bad_ai_text_falls_back(self):
        row = simulation.run(PROFILE, plans(15), ask=lambda _: "모르겠습니다")["rows"][0]
        self.assertFalse(row["ai_used"])

    def test_ai_input_has_no_identity(self):
        rows = [simulation.calculate(PROFILE, s) for s in plans(15)]
        text = simulation.build_ai_input(PROFILE, rows, [])
        self.assertIn("첫 학기", text)
        self.assertNotIn("학번", text)


class CorrectionRangeTest(unittest.TestCase):
    @staticmethod
    def past(*errors):
        return [{"term": "2026-1", "scenario_option": "인턴", "scenario_hours": "10", "scenario_condition": "",
                 "actual_gpa": "3.5", "satisfaction": "3", "user_review": "x", "predicted_gpa": 3.8, "error": e}
                for e in errors]

    def test_no_past_records_no_correction(self):
        self.assertEqual(simulation.personal_correction([])["value"], 0)
        row = simulation.run(PROFILE, plans(15), ask=no_ai)["rows"][0]
        self.assertEqual((row["personal_adjust"], row["expected_gpa"], row["range"]), (0, 3.7, (3.4, 4.0)))

    def test_correction_is_shrunk_by_record_count(self):
        # 1건 −0.3 → 1/3만 반영 = −0.1, 2건 평균 −0.3 → 1/2 = −0.15
        self.assertEqual(simulation.personal_correction(self.past(-0.3))["value"], -0.1)
        self.assertEqual(simulation.personal_correction(self.past(-0.3, -0.3))["value"], -0.15)
        # 한계 ±0.3
        self.assertEqual(simulation.personal_correction(self.past(*[-2.0] * 8))["value"], -0.3)

    def test_correction_applies_without_ai_and_before_ai(self):
        result = simulation.run(PROFILE, plans(15), self.past(-0.3), ask=no_ai)
        row = result["rows"][0]
        self.assertEqual((row["base_gpa"], row["personal_adjust"], row["expected_gpa"]), (3.7, -0.1, 3.6))
        answer = '{"results": [{"scenario_option": "인턴 병행", "adjust": 0.1, "reason": "x"}]}'
        row = simulation.run(PROFILE, plans(15), self.past(-0.3), ask=lambda _: answer)["rows"][0]
        self.assertEqual(row["expected_gpa"], 3.7)   # 3.7 − 0.1(내 기록) + 0.1(AI)

    def test_range_uses_default_until_three_records(self):
        self.assertEqual(simulation.prediction_range(self.past(-0.3, -0.1), {"value": -0.1})["width"], 0.3)
        # 3건 이상: 보정 뒤 남은 오차 평균, 최소 0.1
        span = simulation.prediction_range(self.past(-0.2, -0.2, -0.2), {"value": -0.12})
        self.assertEqual(span["width"], 0.1)
        span = simulation.prediction_range(self.past(-0.6, 0.0, 0.3), {"value": -0.06})
        self.assertEqual(span["width"], 0.32)

    def test_report_and_table_show_range(self):
        table = compare.compare(simulation.run(PROFILE, plans(15), ask=no_ai)["rows"], 25)
        self.assertEqual(compare.table_rows(table)[0]["예상 범위"], "3.40 ~ 4.00")
        self.assertIn("범위 3.40~4.00", report.make_report(table))


class ActivityTypeTest(unittest.TestCase):
    def test_preset_activities_have_expected_type(self):
        self.assertTrue(all(scenario.keyword_study(name) for name in scenario.PRESET_STUDY))
        self.assertFalse(any(scenario.keyword_study(name) for name in scenario.PRESET_OTHER))
        self.assertTrue(set(scenario.SUGGESTED_OPTIONS) <= set(scenario.PRESET_ACTIVITIES))
        for name in scenario.PRESET_ACTIVITIES:   # 목록 이름은 조합 저장 형식과 겹치지 않아야 합니다
            self.assertNotIn("+", name)
            self.assertIsNone(scenario.ACTIVITY_RE.match(name))

    def test_override_marks_only_when_different(self):
        self.assertEqual(scenario.mark_name("토익", True), "[공부] 토익")
        self.assertEqual(scenario.mark_name("시험 감독 알바", False), "[공부 외] 시험 감독 알바")
        self.assertEqual(scenario.mark_name("공부", True), "공부")          # 자동 판단과 같으면 표시 없음
        self.assertEqual(scenario.mark_name("인턴", None), "인턴")
        self.assertTrue(scenario.is_study("[공부] 토익"))
        self.assertFalse(scenario.is_study("[공부 외] 시험 감독 알바"))
        self.assertEqual(scenario.split_mark("[공부] 토익"), ("토익", True))

    def test_override_changes_gpa_and_survives_save(self):
        built = scenario.build_scenarios(
            [{"activities": [{"name": "토익", "hours": 10, "study": True}, {"name": "시험 감독 알바", "hours": 5, "study": False}]}]
        )[0]
        self.assertEqual(built["scenario_option"], "[공부] 토익(10) + [공부 외] 시험 감독 알바(5)")
        row = simulation.calculate(PROFILE, built)
        self.assertEqual(row["label"], "토익 + 시험 감독 알바")
        self.assertEqual([a["study"] for a in row["activities"]], [True, False])
        # 3.8 + (25 − 5 − 15)×0.02 + 10×0.01 = 4.0
        self.assertEqual(row["base_gpa"], 4.0)


class TargetTest(unittest.TestCase):
    def row(self, option, hours):
        return simulation.calculate(PROFILE, {"scenario_option": option, "scenario_hours": hours})

    def test_gpa_for_matches_formula(self):
        for option, hours in [("인턴 병행", 15), ("공부", 15), ("인턴 병행(15) + 공부(5)", 20)]:
            row = self.row(option, hours)
            other = sum(a["hours"] for a in row["activities"] if not a["study"])
            self.assertEqual(simulation.gpa_for(PROFILE, other, row["study_hours"]), row["base_gpa"])

    def test_target_limits(self):
        plan = simulation.target_plan(PROFILE, self.row("인턴 병행", 15), 3.7)
        self.assertEqual((plan["ok"], plan["max_other"]), (True, 15))
        plan = simulation.target_plan(PROFILE, self.row("인턴 병행", 15), 3.9)
        self.assertEqual((plan["ok"], plan["gap"], plan["max_other"]), (False, 0.2, 5))
        plan = simulation.target_plan(PROFILE, self.row("인턴 병행(15) + 공부(5)", 20), 4.0)
        self.assertEqual((plan["max_other"], plan["min_study"]), (2.5, None))   # 공부를 10시간 다 해도 3.8
        plan = simulation.target_plan(PROFILE, self.row("공부", 5), 4.1)
        self.assertEqual((plan["max_other"], plan["min_study"]), (None, 10))
        plan = simulation.target_plan(PROFILE, self.row("인턴 병행", 15), 4.5)
        self.assertEqual(plan["max_other"], -1)   # 공부 외 활동을 0으로 줄여도 부족

    def test_target_not_fooled_by_rounding(self):
        # 동아리 10시간, 목표 3.9: 공부 9.5시간이면 3.895(반올림하면 3.90)라 부족, 10시간이 필요
        plan = simulation.target_plan(PROFILE, self.row("동아리 확대", 10), 3.9)
        self.assertEqual((plan["max_other"], plan["min_study"]), (5, 10))

    def test_target_uses_personal_correction(self):
        plan = simulation.target_plan(PROFILE, self.row("인턴 병행", 15), 3.7, correction=-0.1)
        self.assertEqual((plan["now"], plan["ok"], plan["max_other"]), (3.6, False, 10))


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "simulation_log.csv"
        scenario.save_plan(PROFILE, plans(15, 5), self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_replan_combo_updates_same_row(self):
        two = lambda h: scenario.build_scenarios([{"activities": [{"name": "인턴", "hours": h}, {"name": "공부", "hours": 5}]}])  # noqa: E731
        scenario.save_plan(PROFILE, two(15), self.path)
        scenario.save_plan(PROFILE, two(10), self.path)
        options = [row["scenario_option"] for row in scenario.read_log(self.path)]
        self.assertEqual(options, ["인턴 병행", "학점 집중", "인턴(10) + 공부(5)"])

    def test_read_backup_validates(self):
        good = self.path.read_bytes()
        self.assertEqual(len(scenario.read_backup(good)), 2)
        for bad in [b"a,b,c\n1,2,3\n", good.replace(b",3.8,", b",9.9,"), good.split(b"\n")[0] + b"\n", "x".encode("utf-16")]:
            with self.assertRaises(ValueError):
                scenario.read_backup(bad)

    def test_backup_keeps_multiline_condition(self):
        scenario.save_plan(PROFILE, scenario.build_scenarios(
            [{"scenario_option": "알바", "scenario_hours": 5, "scenario_condition": "주 3일 근무\n시험 기간에도 근무"}]), self.path)
        rows = scenario.read_backup(self.path.read_bytes())
        self.assertEqual(rows[-1]["scenario_condition"], "주 3일 근무\n시험 기간에도 근무")

    def test_same_activity_names_in_two_options_rejected(self):
        with self.assertRaises(ValueError):
            scenario.build_scenarios([
                {"activities": [{"name": "인턴", "hours": 10}, {"name": "공부", "hours": 5}]},
                {"activities": [{"name": "인턴", "hours": 15}, {"name": "공부", "hours": 5}]},
            ])

    def test_import_merge_and_replace(self):
        backup = scenario.read_backup(self.path.read_bytes())
        backup[0].update({"actual_gpa": "3.5", "satisfaction": "4", "user_review": "x"})
        backup.append({**backup[1], "term": "2025-2"})
        result = scenario.import_rows(backup, "merge", self.path)
        self.assertEqual(result, {"added": 1, "updated": 1, "skipped": 1})
        rows = scenario.read_log(self.path)
        self.assertEqual((len(rows), rows[0]["actual_gpa"]), (3, "3.5"))
        scenario.import_rows(backup[:1], "replace", self.path)
        self.assertEqual(len(scenario.read_log(self.path)), 1)


class CompareReportTest(unittest.TestCase):
    def table(self, *hours):
        return compare.compare(simulation.run(PROFILE, plans(*hours), ask=no_ai)["rows"], 25)

    def test_warning_when_hours_exceed_free_time(self):
        for _ in range(10):   # 성공 기준: 10번 시험해 10번 모두 경고
            table = self.table(30, 25, 5)
            self.assertEqual([r["short"] for r in table["rows"]], [True, False, False])
            self.assertEqual(len(table["warnings"]), 1)

    def test_table_rows_same_columns(self):
        rows = compare.table_rows(self.table(15, 5))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["AI 보정"], "AI 보정 없음")

    def test_report_has_notice_and_no_single_answer(self):
        text = report.make_report(self.table(15, 5, 30))
        self.assertIn("추정치이며 결과를 보장하지 않습니다", text)
        self.assertIn("결정은 내가 합니다", text)
        self.assertIn("시간 부족", text)
        for word in ["추천", "정답"]:
            self.assertNotIn(word, text)


class FeedbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "simulation_log.csv"
        scenario.save_plan(PROFILE, plans(15, 5), self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_record_fills_ten_items_and_error(self):
        index, _ = feedback.open_rows(self.path)[0]
        saved = feedback.record_result(index, 3.5, 4, "과제 시간이 부족했다", self.path)
        self.assertEqual(saved["predicted_gpa"], 3.7)
        self.assertEqual(saved["error"], -0.2)
        row = scenario.read_log(self.path)[0]
        self.assertTrue(all(row[key] != "" for key in scenario.LOG_FIELDS))
        self.assertEqual(len(feedback.open_rows(self.path)), 1)

    def test_record_validation(self):
        for args in [(None, 4, "a"), (3.5, 0, "a"), (3.5, 4, "  ")]:
            with self.assertRaises(ValueError):
                feedback.record_result(0, *args, path=self.path)

    def test_predicted_uses_study_type(self):
        index = [i for i, row in feedback.open_rows(self.path) if row["scenario_option"] == "학점 집중"][0]
        saved = feedback.record_result(index, 4.0, 4, "복습 시간을 늘렸다", self.path)
        self.assertEqual(saved["predicted_gpa"], 4.05)

    def test_past_records_exclude_current_term(self):
        feedback.record_result(0, 3.5, 4, "후기", self.path)
        self.assertEqual(feedback.past_records("2026-2", self.path), [])
        self.assertEqual(len(feedback.past_records("2027-1", self.path)), 1)
        self.assertEqual(feedback.mean_abs_error(feedback.history(self.path)), 0.2)

    def test_delete_selected_rows(self):
        self.assertEqual(scenario.delete_rows([0], self.path), 1)
        rows = scenario.read_log(self.path)
        self.assertEqual([row["scenario_option"] for row in rows], ["학점 집중"])
        with self.assertRaises(ValueError):
            scenario.delete_rows([], self.path)
        with self.assertRaises(ValueError):
            scenario.delete_rows([5], self.path)

    def test_clear_log_keeps_header(self):
        scenario.clear_log(self.path)
        self.assertEqual(scenario.read_log(self.path), [])
        self.assertTrue(self.path.read_text(encoding="utf-8-sig").startswith(",".join(scenario.LOG_FIELDS)))
        scenario.save_plan(PROFILE, plans(10), self.path)   # 지운 뒤에도 다시 기록할 수 있습니다
        self.assertEqual(len(scenario.read_log(self.path)), 1)

    def test_filled_row_cannot_be_replanned(self):
        feedback.record_result(0, 3.5, 4, "후기", self.path)
        with self.assertRaises(ValueError):
            scenario.save_plan(PROFILE, plans(10), self.path)



class FakeStream:
    def __init__(self, parts, stop="end_turn"):
        self.text_stream, self.stop = iter(parts), stop

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get_final_message(self):
        return type("Final", (), {"stop_reason": self.stop})()


class FakeClient:
    """Claude 대신 쓰는 가짜 클라이언트: 요청을 기록하고 정해 둔 글을 흘려보냅니다."""
    def __init__(self, parts, stop="end_turn", old_sdk=False):
        self.calls = []
        outer = self

        class Messages:
            def stream(self, **kw):
                outer.calls.append(("plain", kw))
                return FakeStream(parts, stop)

        class BetaMessages:
            def stream(self, **kw):
                if old_sdk:
                    raise TypeError("unexpected keyword argument 'fallbacks'")
                outer.calls.append(("beta", kw))
                return FakeStream(parts, stop)

        self.messages = Messages()
        self.beta = type("Beta", (), {"messages": BetaMessages()})()


RECORD = {"term": "2026-1", "scenario_option": "인턴 병행", "actual_gpa": "3.5", "satisfaction": "4",
          "user_review": "피곤했지만 배운 게 많음", "predicted_gpa": 3.7, "error": -0.2}


class CounselTest(unittest.TestCase):
    def setUp(self):
        self.table = compare.compare(simulation.run(PROFILE, plans(30, 5, 10), ask=no_ai)["rows"], 25)

    def test_context_has_numbers_not_identity(self):
        text = counsel.build_context(PROFILE, self.table, target=3.9)
        self.assertIn("인턴 병행", text)
        self.assertIn("예상 학점 3.40", text)
        self.assertIn("5시간 부족", text)
        self.assertIn("목표 학점 3.90", text)
        self.assertNotIn("학번", text)
        self.assertIn("일반적인 시간 관리", counsel.build_context(None, None))
        only_records = counsel.build_context(None, None, records=[RECORD])
        self.assertIn("실제 3.5", only_records)
        self.assertIn("아직 비교하지", only_records)

    def test_offline_answers_quick_questions(self):
        q = counsel.QUICK_QUESTIONS
        best = counsel.offline_reply(q[0], PROFILE, self.table)
        self.assertLess(best.index("학점 집중"), best.index("인턴 병행"))   # 예상 학점 높은 순
        self.assertIn("5시간 부족", counsel.offline_reply(q[1], PROFILE, self.table))
        self.assertIn("먼저 넣어 주세요", counsel.offline_reply(q[2], PROFILE, self.table))
        self.assertIn("목표 학점 3.90", counsel.offline_reply(q[2], PROFILE, self.table, target=3.9))
        self.assertIn("기록이 없어요", counsel.offline_reply(q[3], PROFILE, self.table))
        self.assertIn("주제를 잘 찾지 못했어요", counsel.offline_reply("아무 질문", PROFILE, self.table))

    def test_offline_without_profile_or_records(self):
        self.assertEqual(counsel.quick_questions(None, []), counsel.START_QUESTIONS)
        self.assertEqual(counsel.quick_questions(self.table, []), counsel.QUICK_QUESTIONS[:3])
        for quick in counsel.START_QUESTIONS:
            self.assertTrue(counsel.offline_reply(quick))          # 아무것도 없어도 답함
        self.assertIn("109", counsel.offline_reply("요즘 너무 지쳐"))
        self.assertIn("아직 비교한 선택지가 없어서", counsel.offline_reply("어떤 선택지가 학점에 유리해?"))
        self.assertIn("하루로 나누면 매일 약 2.1시간", counsel.offline_reply("인턴 15시간 하면?"))

    def test_offline_with_records_only(self):
        records = [RECORD, {**RECORD, "term": "2026-2", "scenario_option": "동아리 확대", "satisfaction": "2",
                            "actual_gpa": "3.9", "predicted_gpa": 3.8, "error": 0.1, "user_review": "바빴다"}]
        self.assertEqual(counsel.quick_questions(None, records), counsel.RECORD_QUESTIONS)
        summary = counsel.offline_reply(counsel.RECORD_QUESTIONS[0], records=records)
        self.assertIn("학기 말 기록 2건", summary)
        self.assertIn("만족도가 가장 높았던 건 **인턴 병행**", summary)
        self.assertIn("“바빴다”", summary)
        tip = counsel.offline_reply(counsel.RECORD_QUESTIONS[2], records=records)
        self.assertIn("동아리 확대", tip)                          # 만족도 낮았던 선택지 짚기
        # 비교 결과가 있어도 기록 질문엔 기록으로 답함
        self.assertIn("학기 말 기록 2건", counsel.offline_reply("지난 기록 정리해 줘", PROFILE, self.table, records=records))

    def test_stream_reply_uses_fallback_and_context(self):
        client = FakeClient(["인턴은 ", "주 5시간까지예요."])
        history = [{"role": "user", "content": "인턴 해도 돼?"}]
        text = "".join(counsel.stream_reply(history, "내 숫자", client=client, model="claude-opus-5-5"))
        self.assertEqual(text, "인턴은 주 5시간까지예요.")
        kind, kw = client.calls[0]
        self.assertEqual((kind, kw["fallbacks"], kw["model"]), ("beta", "default", "claude-opus-5-5"))
        self.assertIn("내 숫자", kw["system"][1]["text"])
        self.assertEqual(kw["messages"], history)

    def test_stream_reply_old_sdk_and_refusal(self):
        client = FakeClient(["답"], stop="refusal", old_sdk=True)
        text = "".join(counsel.stream_reply([{"role": "user", "content": "x"}], "c", client=client, model="m"))
        self.assertEqual(client.calls[0][0], "plain")
        self.assertIn("답할 수 없습니다", text)

    def test_offline_answers_fit_each_question(self):
        ask = lambda q, **kw: counsel.offline_reply(q, PROFILE, self.table, **kw)   # noqa: E731
        questions = ["인턴 해도 될까?", "알바해야 해", "동아리 계속할까?", "시험 기간엔?", "학점 망쳤어", "장학금 지키려면?",
                     "토익 준비할까", "잠을 못 자", "자꾸 미뤄", "수강 몇학점", "휴학할까", "진로가 고민", "너무 고민돼",
                     "인턴 20시간 하면?", "인턴이랑 동아리 중 뭐가 나아?", "안녕"]
        answers = [ask(q) for q in questions]
        self.assertEqual(len(set(answers)), len(questions))           # 질문마다 다른 답
        self.assertIn("주 15시간 → **3.70**", answers[0])             # 내 프로필로 시간별 예상 학점
        self.assertIn("예상 학점 **3.60**", answers[13])               # 질문 속 시간으로 계산
        self.assertIn("남는 자유 시간 **5시간**", answers[13])
        combo = ask("인턴 10시간 공부 5시간 하면 어때")
        self.assertIn("인턴 10시간 + 공부 5시간", combo)
        self.assertIn("예상 학점 **3.85**", combo)
        self.assertIn("168시간", ask("인턴 1000시간 하면?"))
        self.assertIn("인턴 병행", answers[14])
        self.assertIn("동아리 확대", answers[14])
        self.assertIn("행사", ask("동아리 계속할까?", records=[{**RECORD, "scenario_option": "동아리 확대", "user_review": "행사 때 바빴다"}]))

    def test_offline_routes_to_the_right_topic(self):
        ask = lambda q: counsel.offline_reply(q, PROFILE, self.table, records=[RECORD])   # noqa: E731
        self.assertIn("잠과 체력", ask("잠이 부족해"))                 # '부족'이 있어도 시간 부족 목록이 아님
        self.assertIn("시험은", ask("시험 범위 정리 어떻게 해?"))         # '정리'가 있어도 기록 요약이 아님
        self.assertIn("알바는", ask("알바 바꾸고 싶어"))
        self.assertIn("동아리", ask("지난주부터 동아리가 힘들어").split("\n")[0])
        self.assertIn("인턴은", ask("인턴 제일 적당한 시간은?"))          # '제일'이 있어도 순위가 아님
        self.assertIn("토익", ask("감사해요 그런데 토익은?"))
        self.assertIn("학기 말 기록 1건", ask("지난 학기 기록은 어떻게 반영됐어?"))
        self.assertIn("예상 학점만 보면", ask("어떤 선택지가 학점에 유리해?"))
        self.assertIn("주 5시간 부족", ask("시간이 부족한 선택지가 있어?"))

    def test_offline_daily_hours_become_weekly(self):
        text = counsel.offline_reply("공부를 하루에 3시간 하면?", PROFILE, self.table)
        self.assertIn("공부 하루 3시간(주 21시간)", text)
        self.assertIn("남는 자유 시간 **4시간**", text)
        self.assertIn("인턴 15시간", counsel.offline_reply("인턴하면 15시간인데", PROFILE, self.table))
        self.assertIn("168시간", counsel.offline_reply("하루 30시간 공부", PROFILE, self.table))

    def test_offline_follow_up_uses_previous_topic(self):
        history = [{"role": "user", "content": "인턴 해도 될까?"}, {"role": "assistant", "content": "…"},
                   {"role": "user", "content": "더 자세히"}]
        self.assertIn("현장실습", counsel.offline_reply("더 자세히", PROFILE, self.table, history=history))
        self.assertIn("조금만 더 적어", counsel.offline_reply("왜?", history=[{"role": "user", "content": "왜?"}]))


if __name__ == "__main__":
    unittest.main()
