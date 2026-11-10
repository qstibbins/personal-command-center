from fastapi import FastAPI

from pcc.api.captures import router as captures_router


app = FastAPI(
    title="Personal Command Center API",
    version="0.1.0",
)

app.include_router(captures_router)


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "pcc-api"}
