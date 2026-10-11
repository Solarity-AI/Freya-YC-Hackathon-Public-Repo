"""Flow mode: compiler + packed runtime on an invented service (a parcel-locker company, not a bank case)."""
import json

from builder.compiler import flowgraph
from harness import flow_sim

DOC = {
    "openapi": "3.0.3", "info": {"title": "t", "version": "1"},
    "paths": {
        "/members/{memberNo}/lockers": {"get": {
            "operationId": "listLockers",
            "parameters": [{"name": "memberNo", "in": "path", "required": True, "schema": {"type": "string"}}],
            "responses": {"200": {"description": "ok", "content": {"application/json": {"schema": {
                "type": "object", "properties": {"lockers": {"type": "array"}}}}}},
                "404": {"description": "x", "content": {"application/json": {"schema": {
                    "type": "object", "properties": {"error": {"type": "string"}}}}}}}}},
        "/lockers/rent": {"get": {
            "operationId": "getRent",
            "parameters": [{"name": "lockerId", "in": "query", "required": True, "schema": {"type": "string"}}],
            "responses": {"200": {"description": "ok", "content": {"application/json": {"schema": {
                "type": "object", "properties": {"due": {"type": "number"}, "dueDate": {"type": "string"},
                                                 "usd": {"type": "number"}}}}}}}}},
        "/receipts": {"post": {
            "operationId": "sendReceipt",
            "requestBody": {"content": {"application/json": {"schema": {
                "type": "object", "required": ["lockerId"],
                "properties": {"lockerId": {"type": "string"}, "channel": {"type": "string"}}}}}},
            "responses": {"200": {"description": "ok", "content": {"application/json": {"schema": {
                "type": "object", "properties": {"sent": {"type": "boolean"}}}}}}}}},
    }}

SPEC = {
    "mode": "flow", "bank": {"name": "Lockr", "language": "en"},
    "call_variables": {"declared": [{"name": "memberNo"}, {"name": "now"}], "now": "now"},
    "opening": {"line": "Hello, this is Lockr."},
    "lines": {"clarify": "Sorry, I did not catch that.", "goodbye": "Goodbye."},
    "flow": {
        "start": "list", "on_error": "err", "on_unclear": "bye", "currency_words": {"TRY": "lira", "USD": "dollars"},
        "global": [{"id": "human", "desc": "wants a person", "keywords": ["person", "agent"], "next": "xfer"},
                   {"id": "hours", "desc": "asks opening hours", "keywords": ["hours"], "say": "We are open 24/7.",
                    "resume": True}],
        "nodes": {
            "list": {"type": "call", "op": "listLockers", "args": {"memberNo": "$call.memberNo"}, "save": "L",
                     "next": "pick", "on_status": {"404": "none"}},
            "none": {"type": "end", "text": "You have no lockers."},
            "pick": {"type": "select", "list": "L.lockers", "where": {"op": "eq", "a": "$it.active", "b": True},
                     "label": "name", "keys": [{"field": "number", "digits": 4, "ask": "What are its last 4 digits?"}],
                     "ask": "Which locker: <options>?", "save": "lk", "next": "rent", "on_none": "none",
                     "on_fail": "bye"},
            "rent": {"type": "call", "op": "getRent", "args": {"lockerId": "$lk.id"}, "save": "R", "next": "read"},
            "read": {"type": "say", "text": "Locker <lk.name> ending <lk.number|last:4>.",
                     "parts": [{"if": {"op": "gt", "a": "$R.due", "b": 0},
                                "text": "You owe <R.due|money:TRY> by <R.dueDate|date>."},
                               {"if": {"op": "empty", "a": "$R.due"}, "text": "Nothing is due."},
                               {"if": {"op": "gt", "a": "$R.usd", "b": 0}, "text": "Plus <R.usd|money:USD>."}],
                     "next": "offer"},
            "offer": {"type": "ask", "text": "Shall I e-mail the receipt?",
                      "choices": [{"id": "yes", "next": "send"}, {"id": "no", "next": "bye"}]},
            "send": {"type": "call", "op": "sendReceipt", "args": {"lockerId": "$lk.id", "channel": "EMAIL"},
                     "save": "S", "next": "sent"},
            "sent": {"type": "end", "text": "Sent. Goodbye."},
            "xfer": {"type": "end", "text": "Transferring you."},
            "err": {"type": "end", "text": "Technical problem."},
            "bye": {"type": "end", "text": "Goodbye."},
        }}}

LOCKERS = [{"id": "A", "name": "Gold", "number": "1111222233334444", "active": True},
           {"id": "B", "name": "Gold", "number": "5555666677778888", "active": True},
           {"id": "C", "name": "Blue", "number": "9999000011112222", "active": True},
           {"id": "D", "name": "Old", "number": "1", "active": False}]


def fake(method, url, body, headers=None):
    if "/members/404/" in url:
        return 404, {"error": "not found"}
    if "/lockers?" in url or url.endswith("/lockers"):
        return 200, {"lockers": LOCKERS}
    if "/lockers/rent" in url:
        lid = url.split("lockerId=")[1]
        return 200, {"due": 1250.5 if lid == "B" else 0, "dueDate": "2026-10-23", "usd": 12 if lid == "B" else 0}
    if url.endswith("/receipts"):
        assert method == "POST" and body["lockerId"] in ("A", "B", "C")
        return 200, {"sent": True}
    return 500, {}


def T(text, **kw):
    d = {"u_text": text}
    d.update(kw)
    return d


def build():
    ops = flowgraph.flow_ops(DOC, "https://mock.example")
    wf, w = flowgraph.compile_flow(SPEC, ops)
    assert flowgraph.check(wf, w, SPEC) == []
    return json.loads(json.dumps(wf))


def play(turns, member="77"):
    out = []
    return flow_sim.run(build(), turns, {"memberNo": member, "now": "2026-10-12T10:30:00+03:00"}, fire=fake,
                        log=out.append), out


def test_ops_keep_method_path_and_params():
    ops = flowgraph.flow_ops(DOC, "https://mock.example/")
    assert ops["listLockers"]["method"] == "GET" and ops["listLockers"]["params"]["memberNo"]["in"] == "path"
    b = flowgraph._binding(ops["getRent"], {"lockerId"})
    url = b["function"]["parameters"]["properties"]["url"]["default"]
    assert url == "https://mock.example/lockers/rent?lockerId={{b_f_getRent_lockerId}}"
    assert "body" not in b["function"]["parameters"]["properties"]


def test_select_by_name_then_digits_reads_conditional_parts_and_sends():
    res, log = play([T("hi"), T("the gold one", u_kind="answer"), T("7 7 7 8 8 8 8", u_val="8888"),
                     T("yes please", u_kind="yes")])
    said = " ".join(res["said"])
    assert "Which locker: Gold and Blue?" in said
    assert "What are its last 4 digits?" in said
    assert "Locker Gold ending 8888." in said and "You owe 1,250.50 lira by Friday, 23 October." in said
    assert "Plus 12 dollars." in said and "Sent. Goodbye." in said
    assert res["end"] == "bye" and res["calls"] == ["f_listLockers", "f_getRent", "f_sendReceipt"]


def test_unique_label_nothing_due_and_no():
    res, _ = play([T("hello"), T("blue please", u_kind="answer"), T("no thanks", u_kind="no")])
    said = " ".join(res["said"])
    assert "Nothing is due." in said and "Plus" not in said and said.endswith("Goodbye.")
    assert "f_sendReceipt" not in res["calls"]


def test_404_branch_and_global_transfer_and_faq_resume():
    res, _ = play([T("hi")], member="404")
    assert res["said"][-1] == "You have no lockers."
    res, _ = play([T("hi"), T("what are your hours", u_kind="question", u_intent="hours"),
                   T("I want a person", u_intent="human")])
    assert "We are open 24/7. Which locker: Gold and Blue?" in " ".join(res["said"])
    assert res["said"][-1] == "Transferring you."


def test_unclear_reasks_then_fails_over():
    res, _ = play([T("hi"), T("hmm"), T("what"), T("eh")])
    assert res["said"][1].startswith("Sorry, I did not catch that.") and res["said"][-1] == "Goodbye."


def test_turkish_money_and_date():
    from runtime import flow
    c = flow._f_ctx({"spec": {"bank": {"language": "tr"}, "flow": {"currency_words": {"TRY": "TL"}}}, "wiring": {}}, {},
                    {"now": "2026-10-12T10:30:00+03:00"})
    assert flow._f_fmt(c, 1250.5, "money", "TRY") == "1.250,50 TL"
    assert flow._f_fmt(c, "2026-10-23", "date", "") == "23 Ekim Cuma"
    assert flow._f_fmt(c, 5, "money", "XYZ") == "5 XYZ"                 # no name in the Spec: the code itself
    assert flow._f_fmt(c, "1111 2222 3333 4444", "spell", "4") == "4 4 4 4"


def _ctx(text="", en="", kind="none", intent="none", val=""):
    from runtime import flow
    R = {"spec": {"bank": {"language": "tr"}, "flow": SPEC["flow"]}, "wiring": {}}
    return flow._f_ctx(R, {"v": {"L": {"lockers": LOCKERS}}},
                       {"u_text": text, "u_en": en, "u_kind": kind, "u_intent": intent, "u_val": val})


def test_yes_no_words_need_one_side():
    from runtime import flow
    assert flow._f_yesno(_ctx("evet, sorun yok")) == "yes"
    assert flow._f_yesno(_ctx("hayır istemiyorum")) == "no"
    assert flow._f_yesno(_ctx("evet hayır")) == ""
    assert flow._f_yesno(_ctx("bilmem", kind="yes")) == "yes"


def test_label_ignores_shared_words_and_reads_turkish_ordinals():
    from runtime import flow
    nd = {"list": "L.lockers", "label": "<it.name> Locker"}
    c = _ctx("Blue Locker olan")
    assert flow._f_by_label(c, nd, [0, 1, 2]) == [2]
    c = _ctx("locker")
    assert flow._f_by_label(c, nd, [0, 1, 2]) == []
    c = _ctx("ikincisi")
    assert flow._f_by_label(c, nd, [0, 1, 2]) == [2]
    c = _ctx("ilki")
    assert flow._f_by_label(c, nd, [0, 1, 2]) == [0, 1]


def test_global_keywords_lose_to_the_question_choices():
    res, _ = play([T("hi"), T("blue", u_kind="answer"), T("yes, and what are the hours", u_kind="yes")])
    assert "Sent. Goodbye." in res["said"][-1]


def test_api_error_without_route_goes_to_on_error():
    def boom(method, url, body, headers=None):
        return (500, {}) if "/lockers/rent" in url else fake(method, url, body, headers)
    out = []
    res = flow_sim.run(build(), [T("hi"), T("blue", u_kind="answer")], {"memberNo": "77", "now": "2026-10-12"},
                       fire=boom, log=out.append)
    assert res["said"][-1] == "Technical problem."


def test_hedge_is_never_a_yes_and_answer_ahead():
    import copy
    from runtime import flow
    spec = copy.deepcopy(SPEC)
    N = spec["flow"]["nodes"]
    N["offer"] = {"type": "ask", "text": "Change the color?", "choices": [{"id": "yes", "keywords": ["sure"], "next": "pickc"},
                                                                     {"id": "no", "next": "bye"}]}
    N["pickc"] = {"type": "ask", "text": "Which color?", "choices": [{"id": "red", "next": "sent"},
                                                                   {"id": "blue", "next": "bye"}]}
    ops = flowgraph.flow_ops(DOC, "https://mock.example")
    wf, _ = flowgraph.compile_flow(spec, ops)
    out = []
    res = flow_sim.run(json.loads(json.dumps(wf)), [T("hi"), T("blue", u_kind="answer"), T("sure I guess", u_kind="hedge"),
                                                    T("red please", u_intent="red")],
                       {"memberNo": "77", "now": "2026-10-12"}, fire=fake, log=out.append)
    assert res["said"][2].startswith("Sorry") and res["said"][-1] == "Sent. Goodbye."
    assert not any("Which color?" in x for x in res["said"])


import pytest


@pytest.mark.parametrize("store", ["flat", "repr", "json"])
def test_answers_read_in_every_form_the_engine_stores(monkeypatch, store):
    monkeypatch.setattr(flow_sim, "STORE", store)
    res, _ = play([T("hi"), T("the gold one", u_kind="answer"), T("8888", u_val="8888"), T("yes", u_kind="yes")])
    assert "You owe 1,250.50 lira by Friday, 23 October." in " ".join(res["said"])
    assert res["calls"] == ["f_listLockers", "f_getRent", "f_sendReceipt"]


def test_a_question_style_intent_loses_to_the_choice_the_words_name():
    import copy
    spec = copy.deepcopy(SPEC)
    spec["flow"]["nodes"]["offer"]["choices"][0]["keywords"] = ["receipt"]
    spec["flow"]["global"].append({"id": "faq_receipt", "keywords": [], "say": "Receipts are free.", "resume": True})
    ops = flowgraph.flow_ops(DOC, "https://mock.example")
    wf, _ = flowgraph.compile_flow(spec, ops)
    run = lambda turns: flow_sim.run(json.loads(json.dumps(wf)), turns, {"memberNo": "77", "now": "2026-10-12"},
                                     fire=fake, log=lambda *a: None)
    res = run([T("hi"), T("blue", u_kind="answer"), T("I want the receipt", u_kind="answer", u_intent="faq_receipt")])
    assert res["said"][-1] == "Sent. Goodbye."
    res = run([T("hi"), T("blue", u_kind="answer"), T("is the receipt free?", u_kind="question", u_intent="faq_receipt")])
    assert res["said"][-1].startswith("Receipts are free.")


def test_a_call_ending_reading_needs_the_words_to_show_it():
    res, _ = play([T("hi"), T("tell me about all of them", u_intent="human"), T("blue", u_kind="answer"),
                   T("no", u_kind="no")])
    assert "Transferring you." not in res["said"] and res["said"][-1] == "Goodbye."
    res, _ = play([T("hi"), T("give me an agent", u_intent="human")])
    assert res["said"][-1] == "Transferring you."


def test_a_bare_yes_is_never_taken_ahead_for_a_later_question():
    import copy
    spec = copy.deepcopy(SPEC)
    N = spec["flow"]["nodes"]
    N["offer"] = {"type": "ask", "text": "Receipt or color?", "choices": [
        {"id": "receipt", "keywords": ["receipt"], "next": "confirm"}, {"id": "color", "keywords": ["color"], "next": "rent2"},
        {"id": "none", "keywords": ["nothing"], "next": "bye"}]}
    N["confirm"] = {"type": "ask", "text": "Send it?", "choices": [{"id": "yes", "next": "send"}, {"id": "no", "next": "bye"}]}
    N["rent2"] = {"type": "call", "op": "getRent", "args": {"lockerId": "$lk.id"}, "save": "R2", "next": "pickc"}
    N["pickc"] = {"type": "ask", "text": "Which color?", "choices": [{"id": "red", "next": "sent"}, {"id": "blue", "next": "bye"}]}
    ops = flowgraph.flow_ops(DOC, "https://mock.example")
    wf, _ = flowgraph.compile_flow(spec, ops)
    run = lambda turns: flow_sim.run(json.loads(json.dumps(wf)), turns, {"memberNo": "77", "now": "2026-10-12"},
                                     fire=fake, log=lambda *a: None)
    res = run([T("hi"), T("blue", u_kind="answer"), T("evet", u_kind="yes", u_intent="yes")])
    assert "f_sendReceipt" not in res["calls"] and res["said"][-1].endswith("Receipt or color?")
    res = run([T("hi"), T("blue", u_kind="answer"), T("make it red", u_intent="red")])     # ahead through a bank call
    assert res["said"][-1] == "Sent. Goodbye." and "Which color?" not in " ".join(res["said"])
