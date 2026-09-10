from fastapi import FastAPI

app = FastAPI(
    title="ProcurePilot API",
    description="Backend API for the ProcurePilot procurement platform.",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "procurepilot-api",
    }
