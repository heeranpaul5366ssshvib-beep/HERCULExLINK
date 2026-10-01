from examples.demo_rag import run_demo


def test_run_demo_returns_answer():
    ans = run_demo()
    assert ans is not None
    assert "MOCK ANSWER" in ans
