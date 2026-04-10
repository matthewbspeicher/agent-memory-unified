import pytest
from trading.agents.gladiator import Gladiator, Persona

def test_gladiator_init():
    g = Gladiator(name="The Auditor", persona=Persona.AUDITOR)
    assert g.name == "The Auditor"
    assert g.persona == Persona.AUDITOR
    assert "logical" in g.system_prompt.lower()
