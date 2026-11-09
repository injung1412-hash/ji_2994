# -*- coding: utf-8 -*-
"""
로컬 검증 스크립트 — 웹앱과 같은 model.py로 모든 자료를 읽고 검증 결과를 출력합니다.
사용법(저장소 최상위에서):  python tools/verify.py
필요 패키지: numpy, openpyxl  (pip install numpy openpyxl)
"""
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("model", os.path.join(ROOT, "model.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def rd(name):
    with open(os.path.join(ROOT, "data", name), "rb") as f:
        return f.read()


def main():
    m.load_aux(rd("classification-2020.xlsx"), rd("io-2023-stats.xlsx"))
    for key in ["large", "mid", "small", "basic"]:
        info = json.loads(m.load_level(key, rd("io-2023-%s.xlsx" % key)))
        ck = info["check"]
        print("%-16s 부문 %3d | 원표 대조 %s | 계수 최대오차 %.1e | 항등식 최대오차 %.1f백만원"
              % (info["label"], info["n"], "통과" if ck["passed"] else "확인필요",
                 ck["max_coef_residual"], max(ck["identities"].values())))
    for p in json.loads(m.consistency())["pairs"]:
        print("정합성 %s → %s : %s (최대차 %.1f백만원)" % (p["fine"], p["coarse"], "일치" if p["passed"] else "불일치",
                                                   max(p["diff"].values())))
    pc = json.loads(m.press_check())
    print("보도자료·통계표 재현: %d / %d 일치" % (pc["ok"], pc["total"]))
    for c in pc["checks"]:
        if not c["ok"]:
            print("  -", c["table"], c["label"], "공표", c["official"], "계산", c["computed"], "|", c.get("note", ""))
    sim = json.loads(m.simulate("basic", json.dumps({"shocks": [{"code": "0111", "amount": 1000}]})))
    t = sim["totals"]
    print("예시 검증(벼 국산 최종수요 1,000백만원): 생산 %.4f, 수입 %.4f, 부가가치 %.4f 백만원"
          % (t["production"], t["imports"], t["valueAdded"]))
    return 0 if pc["ok"] >= pc["total"] - 3 else 1


if __name__ == "__main__":
    sys.exit(main())
