"""Thin async client for the Home Assistant REST + WebSocket APIs."""
from __future__ import annotations

import asyncio
import itertools
import json
import logging
from typing import Any, Awaitable, Callable

import httpx
import websockets

log = logging.getLogger("homehub.ha")


class HA:
    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token
        self.http = httpx.AsyncClient(base_url=self.url + "/api", headers={"Authorization": f"Bearer {token}"}, timeout=60)
        ws = self.url.replace("http://", "ws://").replace("https://", "wss://")
        self.ws_url = ws + "/websocket" if ws.endswith("/core") else ws + "/api/websocket"
        self._ids = itertools.count(1)
        self._ws = None
        self._lock = asyncio.Lock()

    # ---------------- REST ----------------
    async def get(self, path: str) -> Any:
        r = await self.http.get(path)
        r.raise_for_status()
        return r.json()

    async def states(self) -> list[dict]:
        return await self.get("/states")

    async def config(self) -> dict:
        return await self.get("/config")

    async def call_service(self, domain: str, service: str, data: dict) -> Any:
        r = await self.http.post(f"/services/{domain}/{service}", json=data)
        r.raise_for_status()
        return r.json()

    # ---------------- WebSocket (request/response) ----------------
    async def _connect(self):
        ws = await websockets.connect(self.ws_url, max_size=2**28, ping_interval=30)
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": self.token}))
        msg = json.loads(await ws.recv())
        if msg.get("type") != "auth_ok":
            raise RuntimeError(f"Home Assistant auth failed: {msg}")
        return ws

    async def ws(self, payload: dict) -> Any:
        """Send one command on a shared connection and wait for its result."""
        async with self._lock:
            for attempt in (1, 2):
                try:
                    if self._ws is None:
                        self._ws = await self._connect()
                    mid = next(self._ids)
                    await self._ws.send(json.dumps({"id": mid, **payload}))
                    while True:
                        msg = json.loads(await asyncio.wait_for(self._ws.recv(), 120))
                        if msg.get("id") == mid:
                            if not msg.get("success", True):
                                raise RuntimeError(f"{payload.get('type')}: {msg.get('error')}")
                            return msg.get("result")
                except (websockets.ConnectionClosed, OSError, asyncio.TimeoutError):
                    self._ws = None
                    if attempt == 2:
                        raise

    async def energy_prefs(self) -> dict:
        try:
            return await self.ws({"type": "energy/get_prefs"}) or {}
        except RuntimeError:
            return {}

    async def registries(self) -> tuple[list, list, list]:
        ents = await self.ws({"type": "config/entity_registry/list"})
        devs = await self.ws({"type": "config/device_registry/list"})
        areas = await self.ws({"type": "config/area_registry/list"})
        return ents, devs, areas

    async def statistic_ids(self) -> list[dict]:
        return await self.ws({"type": "recorder/list_statistic_ids"})

    async def statistics(self, ids: list[str], start: str, end: str | None, period: str, types: list[str]) -> dict:
        p = {"type": "recorder/statistics_during_period", "start_time": start, "statistic_ids": ids, "period": period, "types": types}
        if end:
            p["end_time"] = end
        return await self.ws(p) or {}

    # ---------------- WebSocket (live subscription) ----------------
    async def subscribe_states(self, on_change: Callable[[dict], Awaitable[None] | None]) -> None:
        """Run forever, calling on_change(new_state) for every state_changed event."""
        while True:
            try:
                ws = await self._connect()
                await ws.send(json.dumps({"id": 1, "type": "subscribe_events", "event_type": "state_changed"}))
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("type") == "event":
                        ns = msg["event"]["data"].get("new_state")
                        if ns:
                            r = on_change(ns)
                            if asyncio.iscoroutine(r):
                                await r
            except asyncio.CancelledError:
                raise
            except Exception as e:  # reconnect on any failure
                log.warning("live subscription dropped: %s; retrying in 10s", e)
                await asyncio.sleep(10)
