---
name: Bittensor Validator Setup
description: WSL2 validator infrastructure for Subnet 8 — wallet address, deployment state, config details
type: project
---

Bittensor validator wallet created on WSL2 (2026-04-06):
- Wallet name: sta_wallet, hotkey: sta_hotkey
- Coldkey SS58: 5D2bwSZYA6Lxhi76VaT52av6VDYU1fYYSFjzsPmPmM8J7Aqe
- btcli version: 9.20.1, bittensor SDK: 10.2.0
- Wallet path: ~/.bittensor/wallets/ (default)
- WSL2 user: mspeicher, repo: /opt/agent-memory-unified

**Why:** Running a Subnet 8 (Taoshi PTN) validator to collect miner predictions, evaluate accuracy, and set on-chain weights. Trading service code is production-ready; only infrastructure setup was blocking.

**How to apply:** When working on bittensor-related tasks, use this wallet config. Systemd service file at deploy/bittensor-validator.service. The trading service entry point is `api.app:create_app` via uvicorn on port 8080.
