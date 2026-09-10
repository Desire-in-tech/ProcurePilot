from fastapi import FastAPI

from app.api.routes.procurements import router as procurement_router

app = FastAPI(
    title="ProcurePilot API",
    description="Backend API for the ProcurePilot procurement platform.",
    version="0.1.0",
)


app.include_router(procurement_router)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "procurepilot-api",
    }
