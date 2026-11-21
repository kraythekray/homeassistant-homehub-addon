"""Background jobs: keep the home model, live state, statistics and weather up to date."""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
from zoneinfo import ZoneInfo

import httpx

from . import discovery
from .db import DB
from .ha import HA

log = logging.getLogger("homehub.collector")


class Collector:
    def __init__(self, ha: HA, db: DB, settings):
        self.ha, self.db, self.s = ha, db, settings
        self.model: dict = db.get("model") or {}
        self.states: dict[str, dict] = {}
        self.tz = ZoneInfo("UTC")
        self.ready = asyncio.Event()
        self.on_cycle = None  # set by the app: async callable run after each stats refresh

    # ---------------- statistic id sets ----------------
    def stat_sets(self) -> dict[str, list[str]]:
        m = self.model
        e, live = m.get("energy", {}), m.get("live", {})
        energy_ids = [x["energy"] for x in e.get("solar", []) if x.get("energy")]
        for part in ("grid", "battery"):
            energy_ids += [v for v in (e.get(part) or {}).values() if v]
        mean_ids = [v for k, v in live.items() if isinstance(v, str) and k in ("load", "batt_soc", "batt_temp", "grid_import", "grid_export")]
        mean_ids += m.get("sys_temps", [])
        mean_ids += [a["power"] for a in m.get("appliances", [])]
        strings = [x["power"] for x in e.get("solar", []) if x.get("power")]
        mean_ids += strings
        return {"energy": sorted(set(energy_ids)), "mean": sorted(set(mean_ids)), "strings": strings}

    # ---------------- model ----------------
    async def refresh_model(self) -> None:
        states = await self.ha.states()
        ents, devs, areas = await self.ha.registries()
        prefs = await self.ha.energy_prefs()
        cfg = await self.ha.config()
        self.model = discovery.build_model(states, ents, devs, areas, prefs, cfg)
        self.states = {s["entity_id"]: s for s in states}
        self.tz = ZoneInfo(cfg.get("time_zone") or "UTC")
        self.db.put("model", self.model)
        log.info("model: %s", self.model["counts"])

    def on_state(self, ns: dict) -> None:
        self.states[ns["entity_id"]] = ns

    # ---------------- statistics ----------------
    async def _pull(self, ids: list[str], period: str, types: list[str], start: dt.datetime, end: dt.datetime | None = None) -> int:
        n = 0
        for i in range(0, len(ids), 25):
            res = await self.ha.statistics(ids[i:i + 25], start.isoformat(), end.isoformat() if end else None, period, types)
            n += self.db.upsert_stats(period, res)
        return n

    async def backfill(self) -> None:
        sets = self.stat_sets()
        now = dt.datetime.now(dt.timezone.utc)
        done = set(self.db.get("backfilled", []))
        todo_e = [i for i in sets["energy"] if i not in done]
        todo_m = [i for i in sets["mean"] if i not in done]
        if not (todo_e or todo_m):
            return
        log.info("backfilling %d energy + %d power statistics over %d days", len(todo_e), len(todo_m), self.s.backfill_days)
        start = now - dt.timedelta(days=self.s.backfill_days)
        cur = start
        while cur < now:
            nxt = min(cur + dt.timedelta(days=30), now)
            if todo_e:
                await self._pull(todo_e, "hour", ["change"], cur, nxt)
            if todo_m:
                await self._pull(todo_m, "hour", ["mean", "max"], cur, nxt)
            cur = nxt
        if todo_e:
            await self._pull(todo_e, "day", ["change"], start)
        self.db.put("backfilled", sorted(done | set(todo_e) | set(todo_m)))

    async def incremental(self) -> None:
        sets = self.stat_sets()
        now = dt.datetime.now(dt.timezone.utc)
        since = now - dt.timedelta(hours=6)
        await self._pull(sets["energy"], "hour", ["change"], since)
        await self._pull(sets["mean"], "hour", ["mean", "max"], since)
        await self._pull(sets["energy"], "day", ["change"], now - dt.timedelta(days=3))
        # HA keeps 5-minute stats ~10 days; we keep them forever for the solar strings.
        if sets["strings"]:
            last = max((self.db.last_ts(s, "5minute") or 0) for s in sets["strings"])
            start = dt.datetime.fromtimestamp(last, dt.timezone.utc) - dt.timedelta(minutes=15) if last else now - dt.timedelta(days=10)
            await self._pull(sets["strings"], "5minute", ["mean"], start)

    # ---------------- weather (Open-Meteo, no key) ----------------
    async def weather(self) -> None:
        loc = self.model.get("location", {})
        if not self.s.weather_enabled or loc.get("lat") is None:
            return
        p = self.s.weather_precision
        lat, lon = round(loc["lat"], p), round(loc["lon"], p)
        tz = loc.get("tz") or "UTC"
        daily = "temperature_2m_max,temperature_2m_min,temperature_2m_mean,shortwave_radiation_sum,cloud_cover_mean,precipitation_sum,weather_code,precipitation_probability_max"
        async with httpx.AsyncClient(timeout=60) as c:
            first = self.db.get("weather_archive_until")
            start = first or (dt.date.today() - dt.timedelta(days=self.s.backfill_days)).isoformat()
            end = (dt.date.today() - dt.timedelta(days=6)).isoformat()
            if start < end:
                r = await c.get("https://archive-api.open-meteo.com/v1/archive", params={
                    "latitude": lat, "longitude": lon, "start_date": start, "end_date": end, "timezone": tz,
                    "daily": daily.replace(",precipitation_probability_max", "")})
                r.raise_for_status()
                self._store_days(r.json()["daily"], forecast=0)
                self.db.put("weather_archive_until", end)
            r = await c.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": lat, "longitude": lon, "timezone": tz, "past_days": 7, "forecast_days": 8,
                "daily": daily, "hourly": "shortwave_radiation,temperature_2m"})
            r.raise_for_status()
            j = r.json()
        today = dt.datetime.now(self.tz).date().isoformat()
        d = j["daily"]
        self._store_days(d, forecast=None, today=today)
        h = j["hourly"]
        rows = []
        for t, rad, temp in zip(h["time"], h["shortwave_radiation"], h["temperature_2m"]):
            ts = int(dt.datetime.fromisoformat(t).replace(tzinfo=self.tz).timestamp())
            rows.append((ts, rad, temp))
        self.db.upsert_weather_hours(rows)

    def _store_days(self, d: dict, forecast, today: str | None = None) -> None:
        rows = []
        for i, day in enumerate(d["time"]):
            g = lambda k: (d.get(k) or [None] * len(d["time"]))[i]
            tmean = g("temperature_2m_mean")
            if tmean is None and g("temperature_2m_max") is not None:
                tmean = (g("temperature_2m_max") + g("temperature_2m_min")) / 2
            fc = forecast if forecast is not None else int(day >= today)
            rows.append((day, tmean, g("temperature_2m_max"), g("temperature_2m_min"), g("shortwave_radiation_sum"),
                         g("cloud_cover_mean"), g("precipitation_sum"), g("weather_code"), g("precipitation_probability_max"), fc))
        self.db.upsert_weather_days(rows)

    # ---------------- loops ----------------
    async def run(self) -> None:
        await self.refresh_model()
        live = asyncio.create_task(self.ha.subscribe_states(self.on_state))
        try:
            await self.backfill()
        except Exception:
            log.exception("backfill failed")
        tick = 0
        while True:
            try:
                if tick % 12 == 0 and tick:  # hourly: re-discover devices
                    await self.refresh_model()
                    await self.backfill()   # picks up newly added devices
                await self.incremental()
                if tick % 12 == 0:
                    try:
                        await self.weather()
                    except Exception as e:
                        log.warning("weather fetch failed: %s", e)
                if self.on_cycle:
                    await self.on_cycle()
                self.ready.set()
            except Exception:
                log.exception("collector cycle failed")
            tick += 1
            await asyncio.sleep(300)
        live.cancel()
