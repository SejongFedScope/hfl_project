"""B 검사 — 담당 B(윤효연), WBS 3.2.6 · 3.4.3. 실행: python -m tests.test_server"""


def test_assignment_no_violation():
    """pref·random 둘 다 미배정·중복·정원 위반 0"""
    raise NotImplementedError  # TODO 3.2.6


def test_reject_409():
    """Flask test_client: 지난 버전 제출, 배정 안 된 클라 제출 → 409"""
    raise NotImplementedError  # TODO 3.4.3


if __name__ == "__main__":
    test_assignment_no_violation()
    test_reject_409()
    print("ok")
