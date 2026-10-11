"""tools/submit.py final: the single-agent submission.json of the final (team, members, repo, commit, run_command,
workflow, trace, mock_url), with the mock URL taken from the build log's START line and checked."""
import json

import pytest

from tests.test_submit import FakeFreya, make_run, run_main, submit

MOCK = "https://bank-mock.team.workers.dev"


def _final_log(root, rd, mock=MOCK):
    (root / "traces").mkdir(exist_ok=True)
    txt = (rd / "trace.txt").read_text().replace("model_default=claude-opus-5-5",
                                                  "model_default=claude-opus-5-5 input_form=case_folder "
                                                  "mock_url=%s" % mock)
    p = root / "traces" / "final.log"
    p.write_text(txt)
    return p


def test_final_offline_writes_submission_json(tmp_path):
    rd = make_run(tmp_path, name="FreyaBank-Case")
    _final_log(tmp_path, rd)
    code, out, err = run_main(["final", "--offline", "--members", "Member One, Eren X"], tmp_path)
    assert code == 0, err
    sub = json.loads(out)
    assert sub == json.loads((tmp_path / "submission.json").read_text())
    assert sub["members"] == ["Member One", "Eren X"]
    assert sub["run_command"] == "python3 builder/build.py {case_folder} {mock_url}"
    assert sub["workflow"] == "submission/final.workflow.json" and sub["trace"] == "traces/final.log"
    assert sub["mock_url"] == MOCK and sub["team"] == submit.TEAM
    assert json.loads((tmp_path / "submission" / "final.workflow.json").read_text())["workflow_id"]
    # members are kept for the next run
    code, out, _ = run_main(["final", "--offline"], tmp_path)
    assert code == 0 and json.loads(out)["members"] == ["Member One", "Eren X"]


def test_final_needs_members(tmp_path):
    code, _, err = run_main(["final", "--offline"], tmp_path)
    assert code == 2 and "--members" in err


@pytest.mark.parametrize("mock,needle", [
    ("https://x.trycloudflare.com", "temporary"), ("http://bank.workers.dev", "not https"),
    ("https://example-mock.invalid", "placeholder")])
def test_final_refuses_a_bad_mock(tmp_path, mock, needle):
    rd = make_run(tmp_path, name="FreyaBank-Case")
    _final_log(tmp_path, rd, mock)
    code, _, err = run_main(["final", "--offline", "--members", "A"], tmp_path)
    assert code == 1 and needle in err
    assert not (tmp_path / "submission.json").exists()


def test_final_mock_url_flag_wins_and_missing_log(tmp_path):
    code, _, err = run_main(["final", "--offline", "--members", "A"], tmp_path)
    assert code == 1 and "no mock URL" in err
    code, _, err = run_main(["final", "--offline", "--members", "A", "--mock-url", MOCK + "/"], tmp_path)
    assert code == 1 and "no run of brief final" in err


def test_final_online_checks_health_and_version(tmp_path, monkeypatch):
    rd = make_run(tmp_path, name="FreyaBank-Case")
    _final_log(tmp_path, rd)
    monkeypatch.setattr(submit, "_fetch_json", lambda url, timeout=15: {"ok": True})
    code, out, err = run_main(["final", "--members", "A"], tmp_path, fr=FakeFreya())
    assert code == 0, err and json.loads(out)["mock_url"] == MOCK
    monkeypatch.setattr(submit, "_fetch_json", lambda url, timeout=15: {"ok": False})
    code, _, err = run_main(["final", "--members", "A"], tmp_path, fr=FakeFreya())
    assert code == 1 and "/health is not ok" in err

    def boom(url, timeout=15):
        raise OSError("down")
    monkeypatch.setattr(submit, "_fetch_json", boom)
    code, _, err = run_main(["final", "--members", "A"], tmp_path, fr=FakeFreya())
    assert code == 1 and "did not answer" in err


def test_final_freya_runtime_error(tmp_path, monkeypatch):
    rd = make_run(tmp_path, name="FreyaBank-Case")
    _final_log(tmp_path, rd)
    monkeypatch.setattr(submit, "_fetch_json", lambda url, timeout=15: {"ok": True})

    class Down(FakeFreya):
        def api(self, *a, **k):
            raise RuntimeError("HTTP 503")
    code, _, err = run_main(["final", "--members", "A"], tmp_path, fr=Down())
    assert code == 1 and "Freya API error" in err


def test_mock_url_from_log():
    assert submit.mock_url_from_log("[+0.0s] START b | build | x=1 mock_url=https://m.dev/ y") == "https://m.dev"
    assert submit.mock_url_from_log("[+0.0s] START b | build | mock_url=None") is None
    assert submit.mock_url_from_log("nothing") is None


def test_members_file_unreadable(tmp_path):
    (tmp_path / "submission.json").write_text("{bad")
    assert submit._members("", tmp_path) == []
    assert submit._members("A; B ,", tmp_path) == ["A", "B"]
