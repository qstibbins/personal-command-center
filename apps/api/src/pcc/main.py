from fastapi import FastAPI

app = FastAPI(title="Personal Command Center API", version="0.1.0")

@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "pcc-api"}
