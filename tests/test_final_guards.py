"""Guards added before the final: no lint error for a queue the contract does not enumerate; pack cap headroom."""
from builder.compiler import lint
from runtime import bundle


def test_pack_cap_has_headroom_for_a_larger_final_spec():
    assert bundle.PACK_MAX_BYTES >= 95_000


def test_queue_check_skipped_when_contract_has_no_queue_enum():
    src = open(lint.__file__, encoding="utf-8").read()
    assert 'en.get("queue") and s["queue"] not in en["queue"]' in src
    assert 'q and en.get("queue") and q not in en["queue"]' in src
