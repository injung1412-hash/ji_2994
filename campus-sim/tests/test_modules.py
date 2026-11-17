# 모듈 6개 확인 (10주차 완성 확인 방법 기준) — 실행: python3 -m unittest discover -s tests
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import compare, feedback, profile, report, scenario, simulation

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

    def test_filled_row_cannot_be_replanned(self):
        feedback.record_result(0, 3.5, 4, "후기", self.path)
        with self.assertRaises(ValueError):
            scenario.save_plan(PROFILE, plans(10), self.path)


if __name__ == "__main__":
    unittest.main()
