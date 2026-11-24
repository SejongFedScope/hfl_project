"""전체 검사를 unittest 로 — 담당 C (수업 5장 3차시: python -m unittest 로 한 번에)
실행: python -m unittest            (프로젝트 맨 위에서. tests/ 의 검사를 모두 돎)
      python -m unittest tests.test_suite.Learning   (하나만)
각 검사 파일(test_learning·test_server·test_dashboard·test_ui·test_requirements)은 그대로 두고,
그 안의 test_ 함수를 정의된 순서대로 TestCase 메서드로 감싸기만 함 (python -m tests.xxx 로 따로 돌리는 것도 그대로 됨).
"""
import importlib
import inspect
import unittest


def _wrap(module_name, class_name):
    """모듈의 test_ 함수들 → TestCase (메서드 이름에 순번을 붙여 정의 순서대로 돎: 검사끼리 설정을 나눠 쓰는 경우가 있음)"""
    mod = importlib.import_module(module_name)
    funcs = [f for name, f in vars(mod).items() if name.startswith("test_") and inspect.isfunction(f) and f.__module__ == mod.__name__]
    body = {f"test_{i:02d}_{f.__name__[5:]}": (lambda self, f=f: f()) for i, f in enumerate(funcs, 1)}
    return type(class_name, (unittest.TestCase,), body)


Learning = _wrap("tests.test_learning", "Learning")      # 담당 A
Server = _wrap("tests.test_server", "Server")            # 담당 B
Dashboard = _wrap("tests.test_dashboard", "Dashboard")   # 담당 C
Ui = _wrap("tests.test_ui", "Ui")                        # 담당 C (playwright 없으면 안에서 SKIP)


class Requirements(unittest.TestCase):
    """명세 필수 6항목 (공동). 실제 로그가 있어야 함 → 없으면 건너뜀 (먼저 python -m scripts.run_all)"""

    def test_six_items(self):
        from tests import test_requirements
        try:
            test_requirements.main()
        except SystemExit as e:
            if isinstance(e.code, str):
                self.skipTest(e.code)
            self.assertEqual(e.code, 0, "필수 6항목 중 X 가 있음 (위 출력 확인)")


if __name__ == "__main__":
    unittest.main()
