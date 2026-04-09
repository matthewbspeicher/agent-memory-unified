"""Tests for the knowledge signal pre-filter in flush.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from flush import has_knowledge_signal


def test_noise_only_returns_false():
    context = "**Read** /some/file.py\n**Bash** git status\n**User**: yes\n**Assistant**: Done."
    assert has_knowledge_signal(context) is False


def test_empty_returns_false():
    assert has_knowledge_signal("") is False


def test_decision_markers_return_true():
    context = "**User**: I decided to switch to WAL mode for the database config.\n**Assistant**: Good choice."
    assert has_knowledge_signal(context) is True


def test_problem_and_fix_returns_true():
    context = "**User**: There's a bug in the bridge — it crashed overnight.\n**Assistant**: The root cause was a stale handle."
    assert has_knowledge_signal(context) is True


def test_single_write_triggers():
    context = "**Write** trading/storage/knowledge_graph.py\n**Read** trading/config.py"
    assert has_knowledge_signal(context) is True


def test_many_edits_triggers():
    context = "**Edit** f1.py\n**Edit** f2.py\n**Edit** f3.py\n**Edit** f4.py"
    assert has_knowledge_signal(context) is True


def test_user_hint_always_triggers():
    context = "**Read** some_file.py\nUser hint: remember this config change"
    assert has_knowledge_signal(context) is True


def test_remember_this_triggers():
    context = "**Bash** git log\nremember this deployment procedure"
    assert has_knowledge_signal(context) is True


def test_single_marker_not_enough():
    context = "**Bash** python -m pytest\nFAILED: 1 error in test.py\n**User**: ok\n**Assistant**: Let me look."
    assert has_knowledge_signal(context) is False


def test_ansi_codes_stripped():
    context = "\x1b[31mERROR\x1b[0m something\n**User**: yes\n**Assistant**: ok"
    assert has_knowledge_signal(context) is False
