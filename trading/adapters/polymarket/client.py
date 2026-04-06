"""
Polymarket Client wrapper.

Handles L1/L2 authentication, REST CLOB endpoints, and on-chain
interactions (approvals, USDC deposits/withdrawals) via Polygon.
"""

from __future__ import annotations

import json
import logging
import httpx
from pathlib import Path

from eth_account import Account
from py_clob_client.client import ClobClient, ApiCreds
from py_clob_client.constants import POLYGON
from web3 import Web3

logger = logging.getLogger(__name__)

# CTF Exchange + Neg Risk adapter contracts on Polygon
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8fE6Bd8ED4C27"
NEG_RISK_ADAPTER = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"

# USDC on Polygon
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"


class PolymarketClient:
    def __init__(
        self,
        private_key: str,
        funder: str | None = None,
        signature_type: int = 0,  # 0 = EOA, 1 = Poly/Magic
        rpc_url: str = "https://polygon-rpc.com",
        api_key: str | None = None,
        creds_path: str = "data/polymarket_creds.json",
        dry_run: bool = True,
        relayer_api_key: str | None = None,
        relayer_address: str | None = None,
    ):
        self._private_key = private_key
        self._funder = funder
        self._signature_type = signature_type
        self._api_key = api_key
        self._creds_path = creds_path
        self.dry_run = dry_run
        self._relayer_api_key = relayer_api_key
        self._relayer_address = relayer_address

        # Derive wallet from pk
        self._wallet = Account.from_key(private_key)
        self.address = self._wallet.address

        # Initialize base CLOB client (without L2 creds yet)
        self.clob = ClobClient(
            host="https://clob.polymarket.com",
            key=self._private_key,
            chain_id=POLYGON,
            signature_type=self._signature_type,
            funder=self._funder,
        )

        self._w3 = Web3(Web3.HTTPProvider(rpc_url))
        self._usdc = self._w3.eth.contract(
            address=self._w3.to_checksum_address(USDC_ADDRESS),
            abi=[
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function",
                },
                {
                    "constant": False,
                    "inputs": [
                        {"name": "_spender", "type": "address"},
                        {"name": "_value", "type": "uint256"},
                    ],
                    "name": "approve",
                    "outputs": [{"name": "", "type": "bool"}],
                    "type": "function",
                },
                {
                    "constant": True,
                    "inputs": [
                        {"name": "_owner", "type": "address"},
                        {"name": "_spender", "type": "address"},
                    ],
                    "name": "allowance",
                    "outputs": [{"name": "", "type": "uint256"}],
                    "type": "function",
                },
            ],
        )

    # ------------------------------------------------------------------------
    # Auth & Credentials
    # ------------------------------------------------------------------------

    def authenticate(self, creds_path: str | None = None) -> None:
        """
        Two-step auth: load L2 creds from file, or derive them via wallet signing
        if missing/stale. Saves derived creds to `creds_path`.
        """
        path = Path(creds_path or self._creds_path)
        creds_loaded = False

        if path.exists():
            try:
                data = json.loads(path.read_text())
                creds = ApiCreds(
                    api_key=data["api_key"],
                    api_secret=data["api_secret"],
                    api_passphrase=data["api_passphrase"],
                )
                self.clob.set_api_creds(creds)

                # Check validity
                if self.check_health():
                    logger.info(
                        "Polymarket: Loaded valid L2 credentials from %s", creds_path
                    )
                    creds_loaded = True
                else:
                    logger.warning(
                        "Polymarket: Cached L2 credentials stale, re-deriving."
                    )
            except Exception as e:
                logger.warning(
                    "Polymarket: Failed to load L2 credentials from %s: %s",
                    creds_path,
                    e,
                )

        if not creds_loaded:
            logger.info(
                "Polymarket: Deriving new L2 credentials via wallet signature..."
            )
            creds = self.clob.create_or_derive_api_creds()
            self.clob.set_api_creds(creds)

            # Persist
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "api_key": creds.api_key,
                        "api_secret": creds.api_secret,
                        "api_passphrase": creds.api_passphrase,
                    }
                )
            )
            path.chmod(0o600)
            logger.info("Polymarket: Saved new L2 credentials to %s", creds_path)

    def check_health(self) -> bool:
        """Verify the current L2 credentials are valid by querying server time."""
        try:
            res = self.clob.get_server_time()
            return isinstance(res, int) or (isinstance(res, str) and res.isdigit())
        except Exception as e:
            logger.error(f"Polymarket check_health failed: {e}")
            return False

    # ------------------------------------------------------------------------
    # CLOB REST Endpoints
    # ------------------------------------------------------------------------

    def get_market(self, condition_id: str) -> dict:
        return self.clob.get_market(condition_id)

    def get_market_by_slug(self, slug: str) -> dict:
        # The Python SDK doesn't expose a native get_market_by_slug method.
        # We drop down to httpx for HTTP requests
        # endpoint: /markets?slug={slug}
        resp = httpx.get(f"{self.clob.host}/markets?slug={slug}")
        resp.raise_for_status()
        data = resp.json()
        if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
            return data["data"][0]
        return {}

    def get_markets(
        self,
        tag: str = None,
        active: bool = True,
        next_cursor: str = "",
        limit: int = 100,
    ) -> dict:
        # /markets
        params = {"limit": limit}
        if active:
            params["active"] = "true"
        if next_cursor:
            params["next_cursor"] = next_cursor

        # Tags isn't explicitly natively supported in py_clob_client's typing, we use raw get if needed
        resp = httpx.get(f"{self.clob.host}/markets", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_orderbook(self, token_id: str) -> dict:
        return self.clob.get_order_book(token_id)

    def get_trades(self, token_id: str, limit: int = 50) -> dict:
        # Not natively exposed effectively in recent clob SDK sometimes, raw HTTP
        params = {"market": token_id, "limit": limit}
        resp = httpx.get(f"{self.clob.host}/trades", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_orders(self) -> list[dict]:
        return self.clob.get_orders()

    def cancel_order(self, order_id: str) -> dict:
        return self.clob.cancel(order_id)

    # Note: create_order is done directly via SDK in PolymarketOrderManager
    # as it requires OrderBuilder. We expose the clob client for that.

    def get_positions(self) -> list[dict]:
        # Fast path cache
        # (Though we intend to use subgraph primarily in the broker)
        resp = httpx.get(f"{self.clob.host}/positions?user={self.address}")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------------
    # On-Chain Operations (Web3)
    # ------------------------------------------------------------------------

    def get_usdc_balance(self) -> int:
        """Return the raw integer USDC balance (6 decimals)."""
        return self._usdc.functions.balanceOf(self.address).call()

    def setup_approvals(self, dry_run: bool = False) -> None:
        """
        Idempotent dual approval:
        1. USDC -> CTF Exchange
        2. ERC-1155 -> NegRisk Adapter (Requires ConditionalTokens ABI)
        """
        if dry_run:
            logger.info("Polymarket: Skipping on-chain approvals (dry-run mode).")
            return

        MAX_INT = 2**256 - 1

        # 1. Check/Approve USDC to CTF Exchange
        ctf_checksum = self._w3.to_checksum_address(CTF_EXCHANGE)
        allowance = self._usdc.functions.allowance(self.address, ctf_checksum).call()
        if allowance == 0:
            logger.info("Polymarket: Approving USDC for CTF Exchange...")
            txn = self._usdc.functions.approve(ctf_checksum, MAX_INT).build_transaction(
                {
                    "from": self.address,
                    "nonce": self._w3.eth.get_transaction_count(self.address),
                }
            )
            signed = self._w3.eth.account.sign_transaction(
                txn, private_key=self._private_key
            )
            tx_hash = self._w3.eth.send_raw_transaction(
                signed.raw_transaction
            )  # Note: use raw_transaction in v7
            self._w3.eth.wait_for_transaction_receipt(tx_hash)
            logger.info("Polymarket: USDC approved.")

        # 2. Check/Approve ERC-1155 Conditional Tokens to NegRisk Adapter
        # Usually conditional tokens are pre-approved or handled by the ClobClient,
        # but to be safe and thorough as per spec...
        CONDITIONAL_TOKENS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"  # standard CT address on Polygon
        ct_contract = self._w3.eth.contract(
            address=self._w3.to_checksum_address(CONDITIONAL_TOKENS),
            abi=[
                {
                    "constant": True,
                    "inputs": [
                        {"name": "owner", "type": "address"},
                        {"name": "operator", "type": "address"},
                    ],
                    "name": "isApprovedForAll",
                    "outputs": [{"name": "", "type": "bool"}],
                    "type": "function",
                },
                {
                    "constant": False,
                    "inputs": [
                        {"name": "operator", "type": "address"},
                        {"name": "approved", "type": "bool"},
                    ],
                    "name": "setApprovalForAll",
                    "outputs": [],
                    "type": "function",
                },
            ],
        )
        neg_risk_checksum = self._w3.to_checksum_address(NEG_RISK_ADAPTER)
        is_approved = ct_contract.functions.isApprovedForAll(
            self.address, neg_risk_checksum
        ).call()
        if not is_approved:
            logger.info("Polymarket: Approving ERC-1155 for NegRisk Adapter...")
            txn = ct_contract.functions.setApprovalForAll(
                neg_risk_checksum, True
            ).build_transaction(
                {
                    "from": self.address,
                    "nonce": self._w3.eth.get_transaction_count(self.address),
                }
            )
            signed = self._w3.eth.account.sign_transaction(
                txn, private_key=self._private_key
            )
            tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
            self._w3.eth.wait_for_transaction_receipt(tx_hash)
            logger.info("Polymarket: NegRisk approved.")
