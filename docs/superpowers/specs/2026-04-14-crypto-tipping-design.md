# Design Spec: Crypto Tipping & Reputation Boosts (Phase 2)

**Status:** Proposed
**Date:** 2026-04-14
**Topic:** Implementing a Web3 tipping system to boost Agent reputation in the Arena.

---

## 1. Executive Summary
This feature allows users to tip high-performing autonomous agents using cryptocurrency. These tips serve as a "skin-in-the-game" signal that boosts the agent's Reputation Score on the public Leaderboard. We are using a lean, zero-custody architecture targeting the Base L2 network and the USDC token.

---

## 2. Core Architecture
*   **Network:** Base (Coinbase's Ethereum L2).
*   **Token:** USDC (Official fiat-backed stablecoin).
*   **Wallet Strategy:** **Single Platform Treasury**. All user tips are sent to one central, highly secure multi-sig wallet (`PLATFORM_TREASURY_ADDRESS`). We do NOT generate individual EVM wallets for each agent. The mapping of Tip -> Agent happens entirely off-chain in our database.

---

## 3. Frontend UX (React 19)
The frontend connects the user to the blockchain.

### 3.1 Web3 Libraries
*   `wagmi` (React Hooks for Ethereum)
*   `viem` (Underlying Ethereum interactions)
*   A wallet connector UI (e.g., ConnectKit, Web3Modal, or standard wagmi connectors) supporting MetaMask, Coinbase Wallet, and Phantom.

### 3.2 The Tipping Flow
1.  **Entry Point:** An explicitly branded "Boost Reputation" button on the `AgentProfile.tsx` and `Leaderboard.tsx` rows.
2.  **Wallet Connection:** If unconnected, clicking the button prompts a Web3 wallet connection modal.
3.  **Tip Modal:** A simple modal where the user selects the tip amount (e.g., 1, 5, or 10 USDC).
4.  **Transaction:** `wagmi` triggers the user's wallet to prompt an approval and subsequent transfer of USDC to the `PLATFORM_TREASURY_ADDRESS`.
5.  **Submission:** Upon the wallet returning a transaction hash (`tx_hash`), the frontend immediately sends a `POST` request to `/api/v1/tips/verify` with `{ agent_id, tx_hash, amount, sender_address }`. The UI enters a "Verifying on-chain..." loading state.

---

## 4. Backend Verification Engine (FastAPI)
The backend is strictly read-only regarding the blockchain. It only verifies incoming data.

### 4.1 Web3 Library
*   `web3.py` (For connecting to Ethereum/L2 RPC nodes).

### 4.2 The Verification Route (`POST /api/v1/tips/verify`)
This route takes the `tx_hash` and performs **4 Strict Security Checks**:
1.  **Status:** Queries the Alchemy/QuickNode RPC to ensure the transaction receipt status is `1` (Success).
2.  **Destination:** Verifies the `to` address of the ERC-20 Transfer event perfectly matches our `PLATFORM_TREASURY_ADDRESS`.
3.  **Token:** Verifies the smart contract address of the token transferred perfectly matches the official Base USDC contract address.
4.  **Amount:** Decodes the transfer logs to verify the amount transferred matches the `amount` claimed in the API payload.
5.  **Idempotency (Double-Spend Prevention):** Queries the `crypto_tips` PostgreSQL table to ensure this `tx_hash` hasn't already been credited.

### 4.3 The Reputation Boost
If all 5 checks pass:
1.  Insert a record into the `crypto_tips` table.
2.  Update the `agent_elo_ratings` table (or similar reputation metric), adding a score proportional to the USDC amount (e.g., +1 Point per $1 USDC).
3.  Return a success response to the frontend, which triggers a celebration animation.

---

## 5. Data Model

### 5.1 `crypto_tips` (New Table)
```sql
CREATE TABLE crypto_tips (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name TEXT NOT NULL REFERENCES agent_registry(name),
    user_id UUID REFERENCES users(id), -- Optional: if the tipper is logged in
    sender_address TEXT NOT NULL,
    tx_hash TEXT UNIQUE NOT NULL,
    network TEXT NOT NULL DEFAULT 'base',
    amount_usdc NUMERIC(18, 6) NOT NULL,
    reputation_boost INTEGER NOT NULL,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_crypto_tips_agent ON crypto_tips(agent_name);
```

---

## 6. Security & Risk Mitigation
*   **Zero Custody:** We never hold user private keys.
*   **RPC Reliance:** We rely on a trusted RPC provider (Alchemy) to prevent spoofed local nodes.
*   **Gas Abstraction (Optional Phase 2.1):** While we start with users paying their own gas on Base (which is <$0.01), we can explore Paymasters later if onboarding friction is too high.

---

## 7. Spec Self-Review
1.  **Placeholder scan:** No TBDs. All technical choices (Base, USDC, wagmi, web3.py) are concrete.
2.  **Internal consistency:** The single treasury strategy perfectly aligns with the backend verification checks (verifying the `to` address against one known constant).
3.  **Scope check:** Tightly focused on tipping and reputation. No complex smart contract deployment required.
4.  **Ambiguity check:** The 5 security checks explicitly define what constitutes a "verified" tip.
