import logging
from pathlib import Path

from fastapi import Depends, FastAPI, Path as ApiPath, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .data import BigQueryRepository, FPLClient
from .engine import optimize, replacements
from .diagnostics import squad_diagnostics
from .models import Dataset, DomainError, OptimizeRequest, SquadRequest

logger = logging.getLogger(__name__)
app = FastAPI(title="FPL Optimiser", version="1.0.0")
app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)
repository = BigQueryRepository()
fpl = FPLClient()


def get_dataset():
    return repository.get()


@app.exception_handler(DomainError)
async def domain_error(_request: Request, error: DomainError):
    return JSONResponse(status_code=error.status_code, content={"detail": error.message})


def check_version(version: str, dataset: Dataset):
    if version != dataset.version:
        raise DomainError("Player data has refreshed. Reload player data, then try again.", 409)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/players")
def players(dataset: Dataset = Depends(get_dataset)):
    return {**dataset.metadata(), "players": dataset.players}


@app.get("/api/teams/{team_id}")
def team(team_id: int = ApiPath(gt=0, le=2147483647), dataset: Dataset = Depends(get_dataset)):
    return {**dataset.metadata(), **fpl.import_team(team_id, dataset)}


@app.post("/api/replacements")
def replacement_analysis(body: SquadRequest, dataset: Dataset = Depends(get_dataset)):
    check_version(body.dataset_version, dataset)
    return {**dataset.metadata(), "source_gameweek": body.source_gameweek,
            "replacements": replacements(body.squad, {p.id: p for p in dataset.players})}


@app.post("/api/optimize")
def optimization(body: OptimizeRequest, dataset: Dataset = Depends(get_dataset)):
    check_version(body.dataset_version, dataset)
    result = optimize(body, {p.id: p for p in dataset.players})
    if result["players"]:
        result["diagnostics"] = squad_diagnostics(result["players"], result["remaining_budget"], body.objective)
    logger.info("Optimization mode=%s status=%s elapsed=%.3f", body.mode, result["status"], result["elapsed_seconds"])
    return {**dataset.metadata(), "source_gameweek": body.source_gameweek, **result}


# API routes precede the static mount, preserving JSON API 404 responses.
dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if dist.is_dir():
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(dist / "index.html")
