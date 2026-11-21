"""Home Hub web service."""
from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .analytics import Analytics
from .collector import Collector
from .db import DB
from .ha import HA

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("homehub")
STATIC = Path(__file__).resolve().parents[2] / "static"

S = config.load()
db = DB(S.db_path)
ha = HA(S.ha_url, S.ha_token)
col = Collector(ha, db, S)
an = Analytics(db, col, S)
CACHE: dict = {}
VIEWS = ("overview", "energy", "appliances", "habits", "weather", "plan")


async def recompute() -> None:
    """Rebuild every view and re-evaluate alerts. Runs after each collector cycle."""
    def work():
        out = {}
        for v in VIEWS:
            try:
                out[v] = getattr(an, v)()
            except Exception:
                log.exception("view %s failed", v)
        apps = (out.get("appliances") or {}).get("apps")
        raised = db.sync_alerts(an.evaluate_alerts(apps))
        return out, raised
    out, raised = await asyncio.to_thread(work)
    out["_ts"] = int(time.time())
    CACHE.update(out)
    if S.notify_service and raised:
        dom, _, svc = S.notify_service.partition(".")
        for a in raised:
            if a["severity"] in ("crit", "warn"):
                try:
                    await ha.call_service(dom, svc, {"title": f"Home Hub: {a['title']}", "message": a["detail"]})
                    db.mark_notified(a["key"])
                except Exception as e:
                    log.warning("notify failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    col.on_cycle = recompute
    task = asyncio.create_task(col.run())
    yield
    task.cancel()


app = FastAPI(title="Home Hub", lifespan=lifespan)


def view(name: str):
    if name not in CACHE:
        raise HTTPException(503, "Still collecting data from Home Assistant. Try again in a minute.")
    return JSONResponse(CACHE[name])


@app.get("/api/status")
async def status():
    return {"ready": col.ready.is_set(), "updated": CACHE.get("_ts"), "counts": col.model.get("counts"),
            "location": col.model.get("location", {}).get("name"), "addon": S.addon}


@app.get("/api/live")
async def live():
    return {"live": an.live(), "controls": an.controls(), "house": an.house(),
            "appliances": [{"id": a["id"], "w": an.num(a["power"])} for a in col.model.get("appliances", [])]}


@app.get("/api/view/{name}")
async def get_view(name: str):
    if name not in VIEWS:
        raise HTTPException(404)
    return view(name)


@app.get("/api/alerts")
async def alerts():
    now = int(time.time())
    return {"alerts": db.alerts(), "log": db.alert_log(now - 90 * 86400)}


@app.get("/api/battery-temp")
async def battery_temp():
    bt = col.model.get("live", {}).get("batt_temp")
    rows = db.series_full(bt, "hour", int(time.time()) - 7 * 86400) if bt else []
    return {"rows": [[r["ts"], r["mean"], r["max"]] for r in rows]}


@app.post("/api/alerts/{key}/ack")
async def ack(key: str):
    db.ack(key)
    return {"ok": True}


class Toggle(BaseModel):
    entity_id: str


@app.post("/api/control")
async def control(t: Toggle):
    allowed = {c["entity_id"] for c in col.model.get("controls", [])}
    if t.entity_id not in allowed:
        raise HTTPException(403, "That device isn't one of the dashboard's controls.")
    dom = t.entity_id.split(".", 1)[0]
    await ha.call_service(dom, "toggle", {"entity_id": t.entity_id})
    return {"ok": True}


@app.post("/api/refresh")
async def refresh():
    await recompute()
    return {"ok": True, "updated": CACHE.get("_ts")}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


def run():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=S.port, log_level="info")


if __name__ == "__main__":
    run()
