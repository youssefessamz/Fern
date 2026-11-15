import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .engine import Engine, ROOT, EXTRA

app = FastAPI(title="Field Shift")
eng = Engine()
STATIC = ROOT / "app" / "static"


class Entry(BaseModel):
    year: int
    crop: str | None = None


class Req(BaseModel):
    lat: float
    lon: float
    history: list[Entry] = Field(default_factory=list)


@app.get("/api/status")
def status():
    return {"ok": eng.ok, "error": eng.error, "model_loaded": eng.model is not None, "model_error": eng.model_error}


@app.get("/api/cells")
def cells():
    if not eng.ok: raise HTTPException(503, eng.error)
    return {"cells": [{"id": r.cell_id, "lat": float(r.Latitude), "lon": float(r.Longitude)} for r in eng.cells.itertuples()]}


@app.get("/api/crops")
def crops():
    return {"crops": list(eng.crops.index), "other": list(EXTRA)}


@app.post("/api/analyze")
def analyze(req: Req):
    if not eng.ok: raise HTTPException(503, eng.error)
    if not (34.5 <= req.lat <= 42.5 and -120.5 <= req.lon <= -113.5):
        raise HTTPException(422, "Coordinates are outside the supported area: latitude 34.5 to 42.5, longitude -120.5 to -113.5.")
    t = datetime.date.today()
    hist = [h.model_dump() for h in req.history if h.crop]
    return eng.analyze(req.lat, req.lon, hist, t.year + 1 if t.month >= 7 else t.year)


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
