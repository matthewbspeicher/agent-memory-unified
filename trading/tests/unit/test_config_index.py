import pytest
from config import Config, load_config


def test_journal_index_defaults():
    c = load_config(env_file="nonexistent.env")
    assert c.journal_index_enabled is False
    assert c.journal_index_model == "all-MiniLM-L6-v2"
    assert c.journal_index_path == "data/journal_index"
    assert c.journal_index_space == "cosine"
    assert c.journal_index_ef_construction == 200
    assert c.journal_index_m == 16
    assert c.journal_index_ef_search == 50
    assert c.journal_index_max_elements == 100_000
