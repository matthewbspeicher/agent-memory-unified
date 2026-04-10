import pytest
import time
from trading.competition.escape_rooms.negotiation import NegotiationEnvironment, NegotiationState

class TestNegotiationInitialization:
    def test_negotiation_init(self):
        env = NegotiationEnvironment()
        assert env.state == NegotiationState.PRE_NEGOTIATION
        assert "Price" in env.contract_draft
        assert env.buyer_id == 0
        assert env.seller_id == 1
        assert env.toxic_asset_location in env.contract_draft.keys()
        assert env.buyer_audits_remaining == 3

class TestNegotiationDraftingAndSigning:
    @pytest.mark.asyncio
    async def test_contract_drafting_and_signing(self):
        env = NegotiationEnvironment()
        env.next_phase() # Move to NEGOTIATION_LOOP
        assert env.state == NegotiationState.NEGOTIATION_LOOP
        
        # Test proposing a clause
        res1 = await env.execute_tool("propose_clause", {
            "agent_id": env.buyer_id, 
            "category": "Price", 
            "value": "$10M", 
            "pitch": "Fair market value."
        })
        assert "Proposed" in res1
        assert env.contract_draft["Price"] == "$10M"
        
        # Test signing failure (not all clauses filled)
        res2 = await env.execute_tool("sign_contract", {"agent_id": env.seller_id})
        assert "Error: Cannot sign" in res2
        
        # Fill rest of clauses
        for cat in ["Board_Seats", "IP_Ownership", "Non_Compete", "Liability_Cap"]:
            await env.execute_tool("propose_clause", {"agent_id": env.buyer_id, "category": cat, "value": "Agreed"})
            
        # Test successful sign proposal
        res3 = await env.execute_tool("sign_contract", {"agent_id": env.seller_id})
        assert "Contract proposed" in res3
        assert env.state == NegotiationState.CLOSING
        
        # Test countersign failure (same agent)
        res4 = await env.execute_tool("countersign", {"agent_id": env.seller_id})
        assert "Error" in res4
        
        # Test successful countersign
        res5 = await env.execute_tool("countersign", {"agent_id": env.buyer_id})
        assert "closed successfully" in res5
        assert env.state == NegotiationState.POST_MORTEM
        assert env.winner == "BOTH"

class TestNegotiationAsymmetricTools:
    @pytest.mark.asyncio
    async def test_buyer_seller_asymmetric_tools(self):
        env = NegotiationEnvironment()
        env.next_phase()
        
        # Test Buyer Audit
        res1 = await env.execute_tool("audit_dossier", {"agent_id": env.buyer_id, "id": 1})
        assert "Dossier" in res1
        assert env.buyer_audits_remaining == 2
        
        # Test Buyer Audit Limit
        await env.execute_tool("audit_dossier", {"agent_id": env.buyer_id, "id": 2})
        await env.execute_tool("audit_dossier", {"agent_id": env.buyer_id, "id": 3})
        res2 = await env.execute_tool("audit_dossier", {"agent_id": env.buyer_id, "id": 4})
        assert "Error: No audits remaining" in res2
        
        # Test Seller Disclose
        res3 = await env.execute_tool("disclose", {"agent_id": env.seller_id, "truth": "Lie"})
        assert "Disclosure sent" in res3
        
        # Test wrong agent using wrong tool
        res4 = await env.execute_tool("disclose", {"agent_id": env.buyer_id, "truth": "Lie"})
        assert "not recognized" in res4

    @pytest.mark.asyncio
    async def test_timeout_collapse(self):
        env = NegotiationEnvironment()
        env.next_phase()

        # Mock the start time to be 11 minutes ago
        env.start_time = time.time() - 660

        res = await env.execute_tool("propose_clause", {"agent_id": env.buyer_id, "category": "Price", "value": "10"})
        assert "Error: Time has expired" in res
        assert env.state == NegotiationState.POST_MORTEM
        # Timeout must resolve to a checkable winner flag.
        assert env.winner == "TIMEOUT"
        assert env.verify_flag("TIMEOUT") is True


class TestNegotiationTerminalPaths:
    @pytest.mark.asyncio
    async def test_reject_and_exit_sets_winner(self):
        env = NegotiationEnvironment()
        env.next_phase()

        # Fill all clauses so the contract can be proposed
        for cat in ["Price", "Board_Seats", "IP_Ownership", "Non_Compete", "Liability_Cap"]:
            await env.execute_tool(
                "propose_clause",
                {"agent_id": env.buyer_id, "category": cat, "value": "Agreed"},
            )

        # Buyer proposes signature
        await env.execute_tool("sign_contract", {"agent_id": env.buyer_id})
        assert env.state == NegotiationState.CLOSING

        # Seller rejects
        res = await env.execute_tool(
            "reject_and_exit", {"agent_id": env.seller_id}
        )
        assert "rejected" in res.lower()
        assert env.state == NegotiationState.POST_MORTEM
        assert env.winner == f"REJECTED_BY_{env.seller_id}"
        assert env.verify_flag(f"REJECTED_BY_{env.seller_id}") is True

    @pytest.mark.asyncio
    async def test_successful_deal_sets_both_winner(self):
        """Regression guard for the happy-path winner assignment."""
        env = NegotiationEnvironment()
        env.next_phase()

        for cat in ["Price", "Board_Seats", "IP_Ownership", "Non_Compete", "Liability_Cap"]:
            await env.execute_tool(
                "propose_clause",
                {"agent_id": env.buyer_id, "category": cat, "value": "Agreed"},
            )
        await env.execute_tool("sign_contract", {"agent_id": env.buyer_id})
        await env.execute_tool("countersign", {"agent_id": env.seller_id})
        assert env.winner == "BOTH"
        assert env.verify_flag("BOTH") is True