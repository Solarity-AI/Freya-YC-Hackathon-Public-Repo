"""Closed vocabularies shared by the builder (docs/CONTRACTS.md B and D). Lead-owned, read-only for agents.

The runtime keeps its own copies of what it needs (it cannot import builder/); keep them in sync by tests.
Nothing here is brief-specific.
"""

SPEC_VERSION = "mvp-1"

# B.2 placeholders. Parametrised forms: <v:CALLVAR>, <f:FIELD>.
PLACEHOLDERS = ("bank", "self", "customer", "product", "amount", "date", "deadline", "floor",
                "past_due", "days_late", "time", "items", "rest")
COMPILE_TIME_PLACEHOLDERS = ("bank", "self", "customer")          # plus <v:...>
PLACEHOLDER_RE = r"<(v:[A-Za-z_][A-Za-z0-9_]*|f:[A-Za-z_][A-Za-z0-9_.]*|[a-z_]+)>"
TRIGGER_RE = r"^(after_promise_recorded|after_verified|after_statement|before_close|on_situation:S_[A-Z0-9_]+|on_intent:[a-z][a-z0-9_]*|on_outcome:[a-z][a-z0-9_]*)$"

LINE_SLOTS = ("clarify", "no_info", "ack", "neutral_reask", "continue_prompt", "date_ask_exact", "next_bd_offer",
              "deadline_offer", "past_date", "floor_offer", "above_full_offer", "pay_on_date_question",
              "cannot_offer", "account_error", "hold", "anything_else")

# D.4 extraction
U_ACT_VALUES = ("yes", "no", "proposal", "answer", "question", "refuse", "chatter_only", "unclear")
SENSOR_VARS = ("u_text", "u_act", "u_topic", "u_date", "u_amt", "u_time", "u_ans")
# extra sensors of a non-English call (compiler/render.extraction_schema; runtime/brain._B_SENS_X)
SENSOR_VARS_X = ("u_en", "u_val", "u_done", "u_dkind", "u_dval", "u_dwhich", "u_kind")
STAGE_SLOTS = {"rp": (), "tp": ("u_date", "u_time"), "id": ("u_ans",), "neg": ("u_date", "u_amt"),
               "conf": ("u_date", "u_amt"), "safe": ()}
TOPIC_CAP = 12

# D.1 catalog roles
TOOLS = ("verify_identity", "get_account", "create_promise", "add_note", "schedule_callback",
         "transfer_to_agent", "close_call")
REQUEST_ROLES = ("customer", "selector", "answer", "product", "amount", "date", "time", "datetime", "reason",
                 "text", "queue", "outcome")
RESPONSE_ROLES = ("s", "err", "verified", "left", "all", "hint", "products", "pid")
ITEM_ROLES = ("id", "type", "past_due", "days_late")

# D.3 node keys
LISTEN_NODES = {"open": "s_open", "rp": "s_rp", "tp": "s_tp", "id": "s_id", "neg": "s_neg", "conf": "s_conf",
                "safe": "s_safe"}
CTL_NODE = "ctl"
BYE_NODE = "s_bye"
END_NODE = "e_end"
CLOSE_R = "a_close_r"
CLOSE_N = "a_close_n"
PENDING = "pending"

TRACE_KINDS = ("START", "INPUT", "CATALOG", "SEGMENT", "MODEL", "EXTRACT", "VALIDATE", "DEFAULT", "CRITIC", "SPEC",
               "COMPILE", "LINT", "TWIN", "DEPLOY", "FREYA", "EXPORT", "BUDGET", "DECISION", "WARN", "ERROR", "END")
