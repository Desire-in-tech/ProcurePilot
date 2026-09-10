from fastapi import FastAPI

from app.api.routes.auth import router as auth_router
from app.api.routes.procurements import router as procurement_router
from app.api.routes.requirements import router as requirement_router

app = FastAPI(
    title="ProcurePilot API",
    description="Backend API for the ProcurePilot procurement platform.",
    version="0.1.0",
)


app.include_router(auth_router)
app.include_router(procurement_router)
app.include_router(requirement_router)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "procurepilot-api",
    }
