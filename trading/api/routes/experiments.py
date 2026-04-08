import logging
from fastapi import APIRouter, HTTPException, Depends
from api.auth import verify_api_key
from experiments.ab_test import (
    ExperimentConfig,
    ExperimentManager,
    get_experiment_manager,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/experiments", tags=["experiments"], dependencies=[Depends(verify_api_key)])


@router.get("")
async def list_experiments(
    manager: ExperimentManager = Depends(get_experiment_manager),
) -> list[ExperimentConfig]:
    return [exp.config for exp in manager.get_all()]


@router.post("")
async def create_experiment(
    config: ExperimentConfig,
    manager: ExperimentManager = Depends(get_experiment_manager),
) -> ExperimentConfig:
    if manager.get_experiment(config.name):
        raise HTTPException(status_code=400, detail="Experiment already exists")
    manager.add_experiment(config)
    return config


@router.delete("/{name}")
async def delete_experiment(
    name: str, manager: ExperimentManager = Depends(get_experiment_manager)
) -> dict:
    if not manager.get_experiment(name):
        raise HTTPException(status_code=404, detail="Experiment not found")
    manager.remove_experiment(name)
    return {"status": "ok"}
