import pytest
import os
import subprocess


@pytest.mark.integration
def test_identity_schema_applies_cleanly():
    migration_path = os.path.join(
        os.path.dirname(__file__), "../../../scripts/migrations/add-agent-identity.sql"
    )
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            "agent-memory-unified-postgres-1",
            "psql",
            "-U",
            "postgres",
            "-d",
            "agent_memory",
        ],
        input=open(migration_path).read(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Migration failed: {result.stderr}"
    assert "ERROR" not in result.stderr, f"Migration error: {result.stderr}"


@pytest.mark.integration
def test_identity_tables_exist():
    result = subprocess.run(
        [
            "docker",
            "exec",
            "agent-memory-unified-postgres-1",
            "psql",
            "-U",
            "postgres",
            "-d",
            "agent_memory",
            "-t",
            "-c",
            "SELECT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'identity')",
        ],
        capture_output=True,
        text=True,
    )
    assert "t" in result.stdout, "identity schema does not exist"

    result = subprocess.run(
        [
            "docker",
            "exec",
            "agent-memory-unified-postgres-1",
            "psql",
            "-U",
            "postgres",
            "-d",
            "agent_memory",
            "-t",
            "-c",
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'identity' AND table_name = 'agents')",
        ],
        capture_output=True,
        text=True,
    )
    assert "t" in result.stdout, "identity.agents table does not exist"

    result = subprocess.run(
        [
            "docker",
            "exec",
            "agent-memory-unified-postgres-1",
            "psql",
            "-U",
            "postgres",
            "-d",
            "agent_memory",
            "-t",
            "-c",
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'identity' AND table_name = 'audit_log')",
        ],
        capture_output=True,
        text=True,
    )
    assert "t" in result.stdout, "identity.audit_log table does not exist"
