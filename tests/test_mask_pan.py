import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _util import load_module  # noqa: E402

mask_pan = load_module("components/pci-scan/mask_pan.py")


def test_luhn_helper_recognises_valid_and_invalid():
    assert mask_pan.luhn_ok(b"4111111111111111")
    assert not mask_pan.luhn_ok(b"4111111111111112")


def test_luhn_valid_pan_is_redacted():
    counter = [0]
    out = mask_pan.scrub_line(b"card=4111111111111111 end\n", counter)
    assert b"4111111111111111" not in out
    assert b"REDACTED-PAN16" in out
    assert counter[0] == 1


def test_thirteen_digit_valid_pan_is_redacted():
    counter = [0]
    out = mask_pan.scrub_line(b"pan=4222222222222\n", counter)
    assert b"4222222222222" not in out
    assert counter[0] == 1


def test_all_same_digit_run_is_left_intact():
    counter = [0]
    out = mask_pan.scrub_line(b"pad=0000000000000000\n", counter)
    assert b"0000000000000000" in out
    assert counter[0] == 0


def test_non_luhn_run_is_left_intact():
    counter = [0]
    out = mask_pan.scrub_line(b"id=4111111111111112\n", counter)
    assert b"4111111111111112" in out
    assert counter[0] == 0


def test_short_digit_runs_are_ignored():
    counter = [0]
    out = mask_pan.scrub_line(b"qty=411111111111\n", counter)
    assert b"411111111111" in out
    assert counter[0] == 0
