from fastapi import FastAPI

app = FastAPI(title="FlightComp Platform API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}