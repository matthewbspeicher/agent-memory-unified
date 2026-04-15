from fastapi import APIRouter, Depends, UploadFile, File, HTTPException

from adapters.fidelity.parser import parse_fidelity_csv, extract_balances
from api.auth import verify_api_key
from api.identity.dependencies import require_scope
from storage.external import ExternalPortfolioStore


def create_import_router(store: ExternalPortfolioStore) -> APIRouter:
    router = APIRouter(tags=["import"], dependencies=[Depends(verify_api_key)])

    @router.post(
        "/import/fidelity",
        dependencies=[Depends(require_scope("write:orders"))],
    )
    async def import_fidelity(file: UploadFile = File(...)):
        content = (await file.read()).decode("utf-8")
        try:
            positions = parse_fidelity_csv(content)
            balances = extract_balances(content)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"CSV parse error: {e}")

        if not positions and not balances:
            raise HTTPException(status_code=400, detail="No positions found in CSV")

        # Group positions by account
        from collections import defaultdict

        by_account: dict[str, list] = defaultdict(list)
        for p in positions:
            by_account[p.account_id].append(
                {
                    "symbol": p.symbol,
                    "description": p.description,
                    "quantity": str(p.quantity),
                    "last_price": str(p.last_price),
                    "current_value": str(p.current_value),
                    "cost_basis": str(p.cost_basis) if p.cost_basis else None,
                }
            )

        accounts_summary = []
        for account_id, acct_positions in by_account.items():
            bal = balances.get(account_id)
            await store.import_positions(
                broker="fidelity",
                account_id=account_id,
                account_name=bal.account_name if bal else "",
                positions=acct_positions,
                balance={
                    "net_liquidation": str(bal.net_liquidation) if bal else "0",
                    "cash": str(bal.cash) if bal else "0",
                },
            )
            accounts_summary.append(
                {
                    "id": account_id,
                    "name": bal.account_name if bal else "",
                    "positions": len(acct_positions),
                    "value": str(bal.net_liquidation) if bal else "0",
                }
            )

        # Import cash-only accounts that have balances but no positions
        for account_id, bal in balances.items():
            if account_id not in by_account:
                await store.import_positions(
                    broker="fidelity",
                    account_id=account_id,
                    account_name=bal.account_name,
                    positions=[],
                    balance={
                        "net_liquidation": str(bal.net_liquidation),
                        "cash": str(bal.cash),
                    },
                )
                accounts_summary.append(
                    {
                        "id": account_id,
                        "name": bal.account_name,
                        "positions": 0,
                        "value": str(bal.net_liquidation),
                    }
                )

        return {
            "accounts_imported": len(accounts_summary),
            "total_positions": len(positions),
            "accounts": accounts_summary,
        }

    @router.get("/portfolio/external")
    async def get_external_portfolio():
        positions = await store.get_positions()
        balances = await store.get_balances()
        age = await store.get_import_age("fidelity")
        return {
            "positions": positions,
            "balances": balances,
            "import_age_hours": round(age, 1) if age is not None else None,
        }

    return router
