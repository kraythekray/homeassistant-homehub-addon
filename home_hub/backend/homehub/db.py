"""SQLite storage: statistics history, weather, alerts and settings."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS stats(
  stat_id TEXT NOT NULL, period TEXT NOT NULL, ts INTEGER NOT NULL,
  mean REAL, min REAL, max REAL, change REAL,
  PRIMARY KEY(stat_id, period, ts)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS weather_day(
  day TEXT PRIMARY KEY, t_mean REAL, t_max REAL, t_min REAL, radiation REAL, cloud REAL, rain REAL,
  code INTEGER, rain_prob REAL, forecast INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS weather_hour(ts INTEGER PRIMARY KEY, radiation REAL, temp REAL);
CREATE TABLE IF NOT EXISTS alerts(
  key TEXT PRIMARY KEY, severity TEXT, title TEXT, detail TEXT, category TEXT,
  first_seen INTEGER, last_seen INTEGER, resolved_at INTEGER, acked_at INTEGER, notified INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS alert_log(ts INTEGER, key TEXT, severity TEXT, event TEXT);
CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT);
"""


class DB:
    def __init__(self, path: Path):
        self.path = path
        self._local = threading.local()
        with self.conn() as c:
            c.executescript(SCHEMA)

    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30)
            c.row_factory = sqlite3.Row
            self._local.c = c
        return c

    # ---------- kv ----------
    def get(self, k: str, default: Any = None) -> Any:
        r = self.conn().execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return json.loads(r[0]) if r else default

    def put(self, k: str, v: Any) -> None:
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k, json.dumps(v)))

    # ---------- stats ----------
    def upsert_stats(self, period: str, result: dict) -> int:
        rows = []
        for sid, items in result.items():
            for x in items:
                ts = x["start"]
                ts = int(ts / 1000) if isinstance(ts, (int, float)) else int(time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S")))
                rows.append((sid, period, ts, x.get("mean"), x.get("min"), x.get("max"), x.get("change")))
        with self.conn() as c:
            c.executemany("INSERT OR REPLACE INTO stats VALUES(?,?,?,?,?,?,?)", rows)
        return len(rows)

    def series(self, sid: str, period: str, since: int, field: str = "change") -> list[tuple[int, float | None]]:
        q = f"SELECT ts, {field} FROM stats WHERE stat_id=? AND period=? AND ts>=? ORDER BY ts"
        return [(r[0], r[1]) for r in self.conn().execute(q, (sid, period, since))]

    def series_full(self, sid: str, period: str, since: int) -> list[sqlite3.Row]:
        return list(self.conn().execute(
            "SELECT ts, mean, min, max, change FROM stats WHERE stat_id=? AND period=? AND ts>=? ORDER BY ts", (sid, period, since)))

    def last_ts(self, sid: str, period: str) -> int | None:
        r = self.conn().execute("SELECT MAX(ts) FROM stats WHERE stat_id=? AND period=?", (sid, period)).fetchone()
        return r[0]

    # ---------- weather ----------
    def upsert_weather_days(self, rows: Iterable[tuple]) -> None:
        with self.conn() as c:
            c.executemany("INSERT OR REPLACE INTO weather_day VALUES(?,?,?,?,?,?,?,?,?,?)", list(rows))

    def upsert_weather_hours(self, rows: Iterable[tuple]) -> None:
        with self.conn() as c:
            c.executemany("INSERT OR REPLACE INTO weather_hour VALUES(?,?,?)", list(rows))

    def weather_days(self, since_day: str) -> dict[str, sqlite3.Row]:
        return {r["day"]: r for r in self.conn().execute("SELECT * FROM weather_day WHERE day>=? ORDER BY day", (since_day,))}

    def weather_hours(self, since: int) -> list[sqlite3.Row]:
        return list(self.conn().execute("SELECT * FROM weather_hour WHERE ts>=? ORDER BY ts", (since,)))

    # ---------- alerts ----------
    def sync_alerts(self, current: list[dict]) -> list[dict]:
        """Upsert the currently-firing alerts, resolve the rest. Returns newly raised ones."""
        now = int(time.time())
        c = self.conn()
        existing = {r["key"]: dict(r) for r in c.execute("SELECT * FROM alerts")}
        raised, keys = [], set()
        with c:
            for a in current:
                keys.add(a["key"])
                e = existing.get(a["key"])
                if e is None or e["resolved_at"]:
                    c.execute("INSERT OR REPLACE INTO alerts VALUES(?,?,?,?,?,?,?,NULL,NULL,0)",
                              (a["key"], a["severity"], a["title"], a["detail"], a["category"], now, now))
                    c.execute("INSERT INTO alert_log VALUES(?,?,?,?)", (now, a["key"], a["severity"], "raised"))
                    raised.append(a)
                else:
                    c.execute("UPDATE alerts SET severity=?, title=?, detail=?, category=?, last_seen=? WHERE key=?",
                              (a["severity"], a["title"], a["detail"], a["category"], now, a["key"]))
            for k, e in existing.items():
                if k not in keys and not e["resolved_at"]:
                    c.execute("UPDATE alerts SET resolved_at=? WHERE key=?", (now, k))
                    c.execute("INSERT INTO alert_log VALUES(?,?,?,?)", (now, k, e["severity"], "resolved"))
        return raised

    def alerts(self) -> list[dict]:
        return [dict(r) for r in self.conn().execute("SELECT * FROM alerts ORDER BY resolved_at IS NOT NULL, last_seen DESC")]

    def ack(self, key: str) -> None:
        with self.conn() as c:
            c.execute("UPDATE alerts SET acked_at=? WHERE key=?", (int(time.time()), key))

    def mark_notified(self, key: str) -> None:
        with self.conn() as c:
            c.execute("UPDATE alerts SET notified=1 WHERE key=?", (key,))

    def alert_log(self, since: int) -> list[dict]:
        return [dict(r) for r in self.conn().execute("SELECT * FROM alert_log WHERE ts>=? ORDER BY ts", (since,))]
