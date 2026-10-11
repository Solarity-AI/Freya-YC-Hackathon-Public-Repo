"""Vulture whitelist (tools/quality.sh passes this file to vulture next to builder runtime harness).

Each entry is a name that has no static caller in builder/, runtime/ or harness/ but is used dynamically or is a
deliberate test seam / test-harness API. vulture only parses this file; it is never imported or run.
"""
from builder import calendars, contract, llm
from builder.spec import vocab
from harness import mockbank, toy, twin

llm.set_backend  # test seam: tests/test_llm_shape.py swaps the Claude Agent SDK transport for a fake

vocab.LINE_SLOTS  # contract vocabulary (CONTRACTS B); tests/test_contracts.py checks DEFAULT_LINES covers exactly it

# MockBank.call dispatches every bank tool with getattr(self, "_t_" + tool)
mockbank.MockBank._t_verify_identity
mockbank.MockBank._t_get_account
mockbank.MockBank._t_create_promise
mockbank.MockBank._t_add_note
mockbank.MockBank._t_schedule_callback
mockbank.MockBank._t_transfer_to_agent
mockbank.MockBank._t_close_call

toy.replace_ctl  # harness API: tests/test_scenarios.py replays compiled graphs with a scripted ctl
toy.hub_workflow  # harness API: generic replay workflow used by tests/test_twin.py and tests/test_scenarios.py
twin.run_script  # harness API: tests/test_twin.py drives the twin with a list of customer turns

contract.derive_openapi  # contract API: build hook (tests/test_contract.py); build.py uses build_catalog today
calendars.half_days  # calendar API: half-day holidays (tests/test_calendars_tr.py)
calendars.country_for  # calendar API: language/currency -> country (tests/test_calendars_tr.py)
