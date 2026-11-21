"""Everything the dashboard shows that is worked out rather than read: energy balances,
solar string timing, appliance health, habits, weather fits, forecasts, the savings plan
and the alert rules."""
from __future__ import annotations

import datetime as dt
import statistics
import time
from collections import defaultdict
from zoneinfo import ZoneInfo

import numpy as np

DAY = 86400
BAD = ("unavailable", "unknown", "", None)


def fnum(v, d=None):
    try:
        f = float(v)
        return f if np.isfinite(f) else d
    except (TypeError, ValueError):
        return d


class Analytics:
    def __init__(self, db, collector, settings):
        self.db, self.c, self.s = db, collector, settings

    # ------------------------------------------------------------------ basics
    @property
    def m(self):
        return self.c.model

    @property
    def tz(self) -> ZoneInfo:
        return self.c.tz

    def state(self, eid, default=None):
        s = self.c.states.get(eid) if eid else None
        return s["state"] if s and s["state"] not in BAD else default

    def num(self, eid, default=None):
        return fnum(self.state(eid), default)

    def prices(self) -> tuple[float, float]:
        e = self.m.get("energy", {})
        pi = self.s.import_price if self.s.import_price is not None else (e.get("import_price") or 0.0)
        pe = self.s.export_price if self.s.export_price is not None else (e.get("export_price") or 0.0)
        return float(pi), float(pe)

    def battery_kwh(self) -> float:
        if self.s.battery_kwh:
            return self.s.battery_kwh
        live = self.m.get("live", {})
        ah = self.num(live.get("batt_capacity_ah"))
        if not self.m.get("energy", {}).get("battery"):
            return 0.0
        v = self.num(live.get("batt_voltage"), 51.2) or 51.2
        return round((ah or 100) * max(v, 48) / 1000 * 0.9, 1)

    def local(self, ts: int) -> dt.datetime:
        return dt.datetime.fromtimestamp(ts, self.tz)

    def midnight(self, days_ago: int = 0) -> int:
        d = dt.datetime.now(self.tz).replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=days_ago)
        return int(d.timestamp())

    # ------------------------------------------------------------------ energy tables
    def _energy(self, period: str, since: int, cap: float) -> list[dict]:
        e = self.m.get("energy", {})
        parts = {"solar": [x["energy"] for x in e.get("solar", []) if x.get("energy")],
                 "imp": [(e.get("grid") or {}).get("from")], "exp": [(e.get("grid") or {}).get("to")],
                 "dis": [(e.get("battery") or {}).get("from")], "chg": [(e.get("battery") or {}).get("to")]}
        acc: dict[int, dict] = defaultdict(lambda: {"solar": 0.0, "imp": 0.0, "exp": 0.0, "dis": 0.0, "chg": 0.0})
        for k, ids in parts.items():
            for sid in ids:
                if not sid:
                    continue
                for ts, v in self.db.series(sid, period, since):
                    v = v or 0.0
                    if v < 0 or v > cap:  # counter resets and glitches
                        v = 0.0
                    acc[ts][k] += v
        out = []
        for ts in sorted(acc):
            r = acc[ts]
            r["use"] = max(0.0, r["solar"] + r["imp"] - r["exp"] + r["dis"] - r["chg"])
            r["ts"] = ts
            out.append(r)
        return out

    def hourly(self, days: int) -> list[dict]:
        return self._energy("hour", int(time.time()) - days * DAY, 15)

    def daily(self, days: int) -> list[dict]:
        rows = self._energy("day", int(time.time()) - days * DAY, 200)
        for r in rows:
            r["day"] = self.local(r["ts"]).date().isoformat()
        return [r for r in rows if r["use"] > 5]

    def profile(self, rows: list[dict]) -> list[list[float]]:
        acc, n = np.zeros((24, 4)), np.zeros(24)
        for r in rows:
            h = self.local(r["ts"]).hour
            acc[h] += [r["solar"], r["use"], r["imp"], r["exp"]]
            n[h] += 1
        return np.round(acc / np.maximum(n, 1)[:, None], 3).tolist()

    # ------------------------------------------------------------------ live
    def live(self) -> dict:
        lv, e = self.m.get("live", {}), self.m.get("energy", {})
        solar = sum(self.num(x, 0) or 0 for x in (lv.get("solar_power") or []) if x)
        gi, ge = self.num(lv.get("grid_import"), 0), self.num(lv.get("grid_export"), 0)
        bc, bd = self.num(lv.get("batt_charge"), 0), self.num(lv.get("batt_discharge"), 0)
        load = self.num(lv.get("load"))
        if load is None:
            load = max(0, solar + gi - ge + bd - bc)
        strings = [{"name": f"String {i + 1}", "w": self.num(x["power"], 0)} for i, x in enumerate(e.get("solar", [])) if x.get("power")]
        return {
            "ts": int(time.time()),
            "solar": round(solar), "grid_import": round(gi or 0), "grid_export": round(ge or 0),
            "batt_charge": round(bc or 0), "batt_discharge": round(bd or 0), "load": round(load or 0),
            "soc": self.num(lv.get("batt_soc")), "soh": self.num(lv.get("batt_soh")), "batt_temp": self.num(lv.get("batt_temp")),
            "battery_kwh": self.battery_kwh(), "has_battery": bool(e.get("battery")),
            "inverter_state": self.state(lv.get("inverter_state")), "fault": self.state(lv.get("fault")),
            "grid_voltage": self.num(lv.get("grid_voltage")), "grid_frequency": self.num(lv.get("grid_frequency")),
            "co2": self.num(lv.get("co2")), "strings": strings,
            "forecast_today": self.num(lv.get("forecast_today")), "forecast_tomorrow": self.num(lv.get("forecast_tomorrow")),
            "pv_total": self.num(lv.get("pv_total")),
        }

    def controls(self) -> list[dict]:
        out = []
        for c in self.m.get("controls", []):
            s = self.c.states.get(c["entity_id"]) or {}
            out.append({**c, "state": s.get("state", "unavailable")})
        return out

    def house(self) -> list[dict]:
        h, items = self.m.get("house", {}), []
        alarms = [(a, self.state(a)) for a in h.get("alarms", [])]
        alarms = [(a, s) for a, s in alarms if s]
        if alarms:
            armed = [a for a, s in alarms if s.startswith("armed")]
            name = lambda e: (self.c.states[e]["attributes"].get("friendly_name") or e).replace("agentdvr ", "")
            cams = [c for c in h.get("cameras", []) if self.state(c)]
            if armed:
                items.append({"kind": "good", "title": "Alarm", "detail": f"{name(armed[0])}: {self.state(armed[0]).replace('_', ' ')} · {len(cams)} cameras online"})
            else:
                items.append({"kind": "info", "title": "Alarm", "detail": f"Disarmed · {len(cams)} cameras online"})
        ls = h.get("loadshedding")
        if ls:
            stage = self.state(ls, "0")
            items.append({"kind": "good" if str(stage) in ("0", "0.0") else "warn", "title": "Loadshedding",
                          "detail": "Stage 0 · no outages" if str(stage) in ("0", "0.0") else f"Stage {stage}"})
        for cal in h.get("calendars", []):
            s = self.c.states.get(cal) or {}
            a = s.get("attributes", {})
            if a.get("start_time"):
                try:
                    when = dt.datetime.fromisoformat(a["start_time"]).strftime("%A %-d %b, %H:%M")
                except ValueError:
                    when = a["start_time"][:16]
                items.append({"kind": "info", "title": a.get("friendly_name", "Garbage"), "detail": f"{a.get('message', 'Collection')} · {when}"})
            else:
                items.append({"kind": "info", "title": a.get("friendly_name", "Garbage"), "detail": "No collection scheduled soon"})
        home = [self.c.states[p]["attributes"].get("friendly_name", p).split(" ")[0] for p in h.get("persons", []) if self.state(p) == "home"]
        if h.get("persons"):
            items.append({"kind": "good" if home else "info", "title": "Who's home", "detail": (", ".join(home) + (" is home" if len(home) == 1 else " are home")) if home else "Nobody is home"})
        if h.get("rain_sensor"):
            wet = self.state(h["rain_sensor"]) == "on"
            items.append({"kind": "info", "title": "Garden", "detail": "Rain detected" if wet else "Rain sensor dry"})
        return items

    # ------------------------------------------------------------------ overview
    def overview(self) -> dict:
        pi, pe = self.prices()
        hrs = self.hourly(57)
        t0 = self.midnight()
        today = [r for r in hrs if r["ts"] >= t0]
        prof = self.profile([r for r in hrs if r["ts"] < t0])
        tot = lambda k, rows: sum(r[k] for r in rows)
        d30 = self.daily(31)
        use30 = tot("use", d30) or 1
        self30 = (use30 - tot("imp", d30)) / use30 * 100
        now_h = self.local(int(time.time())).hour
        typical_so_far = sum(p[1] for p in prof[:now_h + 1])
        s, u, i, e = (tot(k, today) for k in ("solar", "use", "imp", "exp"))
        return {
            "today": [[self.local(r["ts"]).hour, round(r["solar"], 2), round(r["use"], 2), round(r["imp"], 2), round(r["exp"], 2)] for r in today],
            "profile": prof,
            "kpi": {"solar": round(s, 1), "use": round(u, 1), "imp": round(i, 1), "exp": round(e, 1),
                    "cost_in": round(i * pi, 2), "credit_out": round(e * pe, 2), "net_cost": round(i * pi - e * pe, 2),
                    "self_pct": round((u - i) / u * 100) if u else None, "self30": round(self30),
                    "typical_so_far": round(typical_so_far, 1)},
            "prices": {"import": pi, "export": pe, "currency": self.m.get("location", {}).get("currency", "ZAR")},
        }

    # ------------------------------------------------------------------ solar strings
    def strings(self) -> dict:
        e = self.m.get("energy", {})
        ids = [x["power"] for x in e.get("solar", []) if x.get("power")]
        since = int(time.time()) - 10 * DAY
        out = []
        for n, sid in enumerate(ids):
            rows = self.db.series(sid, "5minute", since, "mean")
            slots, days = defaultdict(list), defaultdict(list)
            for ts, v in rows:
                t = self.local(ts)
                mi = t.hour * 60 + t.minute
                slots[mi // 15].append(v or 0)
                days[t.date().isoformat()].append((mi, v or 0))
            curve = [round(float(np.mean(slots[k]))) if slots[k] else 0 for k in range(96)]
            peak_w = max(curve) if curve else 0
            thr = 500 if peak_w > 1200 else max(50, round(peak_w * 0.3))
            ramps = []
            for d, pts in sorted(days.items()):
                pts.sort()
                on = [mi for mi, v in pts if v >= thr]
                if on:
                    pk = max(pts, key=lambda p: p[1])
                    ramps.append([d, on[0], on[-1], pk[0], round(pk[1])])
            month = defaultdict(lambda: defaultdict(list))
            for ts, v in self.db.series(sid, "hour", int(time.time()) - 365 * DAY, "mean"):
                t = self.local(ts)
                month[t.strftime("%Y-%m")][t.hour].append(v or 0)
            monthly = {k: [round(float(np.mean(h[i]))) if h[i] else 0 for i in range(24)] for k, h in sorted(month.items())}
            # energy share over last 7 days, for imbalance checks
            wk = sum((v or 0) for ts, v in self.db.series(sid, "hour", int(time.time()) - 7 * DAY, "mean")) / 1000
            out.append({"name": f"String {n + 1}", "entity": sid, "curve": curve, "ramps": ramps, "monthly": monthly, "threshold": thr, "kwh7": round(wk, 1)})
        return {"strings": out}

    # ------------------------------------------------------------------ energy view
    def yield_by_month(self, days) -> list[list]:
        wx = self.db.weather_days("2000-01-01")
        acc = defaultdict(lambda: [0.0, 0.0])
        for r in days:
            w = wx.get(r["day"])
            if w and w["radiation"] and not w["forecast"]:
                a = acc[r["day"][:7]]
                a[0] += r["solar"]
                a[1] += w["radiation"]
        return [[k, round(s / rad, 3)] for k, (s, rad) in sorted(acc.items()) if rad > 50]

    def energy(self) -> dict:
        pi, pe = self.prices()
        days = self.daily(366)
        d30 = days[-30:]
        S, U, I, E = (sum(r[k] for r in d30) for k in ("solar", "use", "imp", "exp"))
        CH, DI = sum(r["chg"] for r in d30), sum(r["dis"] for r in d30)
        batt_in = min(CH, max(0, S - E))
        hrs = self.hourly(56)
        y = self.yield_by_month(days)
        best = max((v for _, v in y[:-1]), default=None)
        return {
            "totals30": {"solar": round(S), "use": round(U), "imp": round(I), "exp": round(E), "chg": round(CH), "dis": round(DI),
                         "self_pct": round((U - I) / U * 100) if U else 0,
                         "saved": round((S - E) * pi + E * pe), "saved_self": round((S - E) * pi), "credit": round(E * pe)},
            "sankey": {"solar_house": round(max(0, S - E - batt_in)), "solar_batt": round(batt_in), "solar_grid": round(E),
                       "batt_house": round(DI), "grid_house": round(I)},
            "lifetime_solar": self.num(self.m.get("live", {}).get("pv_total")),
            "yield": y, "yield_best": best,
            "calendar": [[r["day"], round(max(0, (r["use"] - r["imp"]) / r["use"] * 100))] for r in days],
            "profile": self.profile(hrs),
            **self.strings(),
            "prices": {"import": pi, "export": pe},
        }

    # ------------------------------------------------------------------ appliances
    def appliance_health(self) -> list[dict]:
        now = int(time.time())
        out = []
        for a in self.m.get("appliances", []):
            rows = self.db.series_full(a["power"], "hour", now - 365 * DAY)
            if not rows:
                out.append({**a, "status": "off" if not a["available"] else "new", "score": None, "note": "No history yet", "spark": [], "months": [], "kwh56": 0})
                continue
            means = np.array([r["mean"] or 0 for r in rows])
            maxes = np.array([r["max"] or 0 for r in rows])
            ts = np.array([r["ts"] for r in rows])
            on_share = float((means > 5).mean())
            continuous = bool(a.get("always_on")) or (on_share > 0.85 and float(means.mean()) > 40)
            p95 = float(np.percentile(maxes, 95)) if len(maxes) else 0
            run_thr = max(50.0, 0.5 * p95)

            def metric(mask):
                m, x = means[mask], maxes[mask]
                if not len(m):
                    return None
                if continuous:
                    return float(m.mean())
                runs = x[x >= run_thr]
                return float(np.percentile(runs, 75)) if len(runs) >= 5 else None

            months = defaultdict(list)
            for i, t in enumerate(ts):
                months[self.local(int(t)).strftime("%Y-%m")].append(i)
            mlist = sorted(months)[-7:]
            spark = []
            for mo in mlist:
                idx = np.array(months[mo])
                mask = np.zeros(len(ts), bool)
                mask[idx] = True
                spark.append([mo, None if metric(mask) is None else round(metric(mask), 1), round(float(means[idx].sum()) / 1000, 1)])
            recent = metric(ts >= now - 30 * DAY)
            base_vals = [v for _, v, _ in spark[:-2] if v is not None]
            baseline = float(np.median(base_vals)) if len(base_vals) >= 2 else None
            spread = max(float(np.std(base_vals)) if len(base_vals) >= 2 else 0, (baseline or 0) * 0.06)
            change = (recent / baseline - 1) if (recent is not None and baseline) else None
            kwh56 = float(means[ts >= now - 56 * DAY].sum()) / 1000
            status, note, score = "good", "", 96
            unit = "W avg" if continuous else "W running"
            if not a["available"] and not (ts >= now - DAY).any():
                status, note, score = "off", "Not reporting to Home Assistant", None
            elif change is None:
                status, note, score = "new", "Learning its normal pattern", None
            else:
                pct = round(change * 100)
                if continuous:
                    if change > 0.12:
                        status, note = "warn", f"Average draw up {pct}% ({baseline:.0f} → {recent:.0f} W). It's running longer than it used to."
                    else:
                        note = f"Average draw {recent:.0f} W, in its normal range."
                else:
                    prev = spark[-2][1] if len(spark) >= 2 else None
                    prev_chg = (prev / baseline - 1) if (prev and baseline) else 0
                    if abs(change) > 0.15 and abs(prev_chg) > 0.15 and (prev_chg > 0) == (change > 0):
                        status = "warn"
                        note = (f"Running draw {'up' if change > 0 else 'down'} {abs(pct)}% ({baseline:,.0f} → {recent:,.0f} W). "
                                + ("Rising draw can mean a worn motor or blocked filter." if change > 0 else "Falling draw can mean a failing element or a part not engaging."))
                    else:
                        note = f"Running draw steady at {recent / 1000:.2f} kW."
                score = int(max(20, min(99, 98 - abs(change) * 220))) if status == "warn" else int(max(85, min(99, 98 - abs(change) * 80)))
            # Stopped-fridge check: an always-on appliance that has gone silent.
            last3 = means[ts >= now - 4 * 3600][-3:]
            if a.get("always_on") and a["available"] and len(last3) == 3 and baseline and baseline > 20 and float(last3.max()) < 3:
                status, score, note = "crit", 10, "Drawing no power for 3 hours. Check it's switched on and cold."
            out.append({**a, "status": status, "score": score, "note": note, "continuous": bool(continuous), "unit": unit,
                        "spark": spark, "baseline": baseline, "spread": spread, "recent": recent, "change": change,
                        "kwh56": round(kwh56, 1), "now_w": self.num(a["power"])})
        return out

    def appliances(self) -> dict:
        pi, _ = self.prices()
        apps = self.appliance_health()
        hrs = self.hourly(56)
        use56 = sum(r["use"] for r in hrs)
        monitored = sum(a["kwh56"] for a in apps)
        return {"apps": apps, "use56": round(use56), "monitored56": round(monitored), "price": pi}

    # ------------------------------------------------------------------ habits
    def habits(self) -> dict:
        hrs = self.hourly(56)
        heat, cnt = np.zeros((7, 24)), np.zeros((7, 24))
        night = []
        for r in hrs:
            t = self.local(r["ts"])
            heat[t.weekday(), t.hour] += r["use"]
            cnt[t.weekday(), t.hour] += 1
            if 1 <= t.hour <= 4:
                night.append(r["use"])
        heat = np.round(heat / np.maximum(cnt, 1), 2)
        base = float(np.percentile(night, 20)) if night else 0
        now = int(time.time())
        clock = []
        for a in self.m.get("appliances", []):
            byh = np.zeros(24)
            for ts, v in self.db.series(a["power"], "hour", now - 56 * DAY, "mean"):
                byh[self.local(ts).hour] += (v or 0) / 1000
            tot = byh.sum()
            if tot < 1:
                continue
            clock.append({"name": a["name"], "byh": np.round(byh / 56, 3).tolist(), "kwh56": round(float(tot), 1),
                          "solar_share": round(float(byh[9:15].sum() / tot * 100)), "always_on": a.get("always_on", False),
                          "peaks": sorted(int(h) for h in np.argsort(byh)[-2:])})
        clock.sort(key=lambda x: -x["kwh56"])
        wk = heat[:5].sum(axis=1).mean() if heat.any() else 0
        we = heat[5:].sum(axis=1).mean() if heat.any() else 0
        return {"heat": heat.tolist(), "base_kw": round(base, 2), "clock": clock, "weekend_pct": round((we / wk - 1) * 100) if wk else 0}

    # ------------------------------------------------------------------ weather + forecast
    def fits(self, days) -> dict:
        wx = self.db.weather_days("2000-01-01")
        pts = [(wx[r["day"]]["t_mean"], r["use"], wx[r["day"]]["radiation"], r["solar"], r["day"]) for r in days
               if r["day"] in wx and wx[r["day"]]["t_mean"] is not None and wx[r["day"]]["radiation"] and not wx[r["day"]]["forecast"]]
        if len(pts) < 10:
            return {"points": pts, "slope": 0, "intercept": float(np.mean([r["use"] for r in days]) if days else 0), "r": 0, "yield": None}
        A = np.array([p[:4] for p in pts], float)
        slope, intercept = np.polyfit(A[:, 0], A[:, 1], 1)
        r = float(np.corrcoef(A[:, 0], A[:, 1])[0, 1])
        recent = A[-14:]
        yld = float(np.median(recent[:, 3] / np.maximum(recent[:, 2], 0.1)))
        return {"points": [[round(p[0], 1), round(p[1], 1), round(p[2], 1), round(p[3], 1), p[4]] for p in pts],
                "slope": round(float(slope), 3), "intercept": round(float(intercept), 2), "r": round(r, 2), "yield": round(yld, 3)}

    def forecast(self, days=None, fits=None) -> list[list]:
        days = days if days is not None else self.daily(70)
        fits = fits or self.fits(days)
        hrs = self.hourly(56)
        prof = np.array(self.profile(hrs))
        usep = prof[:, 1] / max(prof[:, 1].sum(), 1e-6)
        by_wd = defaultdict(list)
        for r in days[-56:]:
            by_wd[dt.date.fromisoformat(r["day"]).weekday()].append(r["use"])
        wx = self.db.weather_days(dt.datetime.now(self.tz).date().isoformat())
        recent_t = [w["t_mean"] for k, w in self.db.weather_days((dt.date.today() - dt.timedelta(days=56)).isoformat()).items() if w["t_mean"] is not None and not w["forecast"]]
        avg_t = float(np.mean(recent_t)) if recent_t else 20
        hours = {r["ts"]: r for r in self.db.weather_hours(self.midnight())}
        cap = self.battery_kwh()
        soc = (self.num(self.m.get("live", {}).get("batt_soc"), 50) or 50) / 100 * cap
        yld = fits.get("yield") or 0.7
        out = []
        for day, w in list(wx.items())[:7]:
            d0 = int(dt.datetime.fromisoformat(day).replace(tzinfo=self.tz).timestamp())
            wd = dt.date.fromisoformat(day).weekday()
            base_use = float(np.mean(by_wd[wd])) if by_wd[wd] else fits["intercept"]
            use = max(5.0, base_use + fits["slope"] * ((w["t_mean"] or avg_t) - avg_t))
            sol_h = [((hours.get(d0 + h * 3600) or {"radiation": 0})["radiation"] or 0) * 0.0036 * yld for h in range(24)]
            if not any(sol_h) and w["radiation"]:
                sol_h = list(prof[:, 0] / max(prof[:, 0].sum(), 1e-6) * w["radiation"] * yld)
            imp = exp = 0.0
            for h in range(24):
                net = sol_h[h] - use * usep[h]
                if net > 0:
                    c = min(net, cap - soc); soc += c; exp += net - c
                else:
                    d = min(-net, soc - 0.1 * cap) if cap else 0; soc -= d; imp += -net - d
            out.append([day, round(sum(sol_h), 1), round(use, 1), round(imp, 1), round(exp, 1),
                        w["t_max"], w["t_min"], w["code"], w["rain_prob"], w["cloud"]])
        return out

    def weather(self) -> dict:
        days = self.daily(366)
        fits = self.fits(days)
        return {"fits": fits, "forecast": self.forecast(days[-70:], fits)}

    # ------------------------------------------------------------------ savings plan
    def plan(self) -> dict:
        pi, pe = self.prices()
        hrs = self.hourly(56)
        if len(hrs) < 24 * 14:
            return {"ready": False}
        apps = {c["name"]: c for c in self.habits()["clock"]}
        n_days = len(hrs) / 24
        cap0 = self.battery_kwh()
        kwp = self.s.panel_kwp or round(max(r["solar"] for r in hrs) / 0.85, 1) or 5

        def sim(cap=cap0, solar_x=1.0, shift=(), base_cut=0.0):
            soc, I, E = cap * 0.5, 0.0, 0.0
            mv = {n: (sum(apps[n]["byh"]) - sum(apps[n]["byh"][9:15])) for n in shift if n in apps}
            for r in hrs:
                h = self.local(r["ts"]).hour
                u = max(0.0, r["use"] - base_cut)
                for n, off in mv.items():
                    u += off / 6 if 9 <= h < 15 else -apps[n]["byh"][h]
                u, s = max(u, 0.0), r["solar"] * solar_x
                net = s - u
                if net > 0:
                    c = min(net, cap - soc); soc += c; E += net - c
                else:
                    d = min(-net, max(0.0, soc - 0.1 * cap)); soc -= d; I += -net - d
            I, E = I / n_days * 30, E / n_days * 30
            return {"imp": round(I), "exp": round(E), "net": round(I - E), "bill": round(I * pi - E * pe)}

        base = sim()
        ylds = [v for _, v in self.yield_by_month(self.daily(366))]
        restore = None
        if len(ylds) >= 3 and ylds[-1] < 0.6 * max(ylds[:-1]):
            restore = min(1.5, (max(ylds[:-1]) * 0.72) / ylds[-1])
        flex = __import__("re").compile(r"pool|pump|geyser|water heater|dishwasher|washing|dryer|charger|heat pump|\bev\b", __import__("re").I)
        shiftable = [n for n, c in apps.items() if flex.search(n) and not c["always_on"] and c["kwh56"] > 8 and c["solar_share"] < 75]
        base_kw = self.habits()["base_kw"]
        actions, cfg = [], {"cap": cap0, "solar_x": 1.0, "shift": (), "base_cut": 0.0}
        equal = abs(pi - pe) < 1e-6

        def add(key, title, desc, cost, change, default):
            prev = sim(**cfg)
            cfg.update(change)
            new = sim(**cfg)
            actions.append({"key": key, "title": title, "desc": desc, "cost": cost, "default": default,
                            "before": prev, "after": new, "net_delta": prev["net"] - new["net"], "imp_delta": prev["imp"] - new["imp"],
                            "saving": prev["bill"] - new["bill"]})

        if restore:
            add("restore", "Restore panel output", f"Clean the panels and check the strings. Brings yield back to a normal level for the season ({round((restore - 1) * 100)}% more solar).", "R0–R1,500", {"solar_x": restore}, True)
        if shiftable:
            note = "Your buy and sell rates are equal, so this doesn't change the bill. It keeps more of the house on your own power through loadshedding." if equal else "Uses your own solar instead of selling it cheaply and buying back."
            add("shift", f"Shift {', '.join(n.lower() for n in shiftable[:3])} to 10:00–14:00", f"Timers in Home Assistant. {note}", "Free", {"shift": tuple(shiftable)}, not equal)
        if base_kw > 0.3:
            add("base", "Cut always-on load by 150 W", "Find standby drains with the smart plugs. Fix the offline ones first.", "Free", {"base_cut": 0.15}, True)
        if cap0:
            add("battery", "Add a 10 kWh battery", "Stores midday solar for the evening." + (" At equal rates it doesn't lower the bill; it's backup for loadshedding." if equal else ""), "≈ R45,000", {"cap": cap0 + 10}, False)
        cur = sim(**cfg)
        if cur["net"] > 0:
            for add_kwp in [x / 2 for x in range(1, 41)]:
                trial = sim(**{**cfg, "solar_x": cfg["solar_x"] * (kwp + add_kwp) / kwp})
                if trial["net"] <= 0:
                    add("panels", f"Add {add_kwp:g} kWp of panels", f"About {round(add_kwp * 1000 / 550)} more 550 W panels.", f"≈ R{round(add_kwp * 9000):,}", {"solar_x": cfg["solar_x"] * (kwp + add_kwp) / kwp}, False)
                    break
        return {"ready": True, "base": base, "actions": actions, "prices": {"import": pi, "export": pe}, "equal_rates": equal, "kwp": kwp, "battery_kwh": cap0}

    # ------------------------------------------------------------------ alert rules
    def evaluate_alerts(self, apps=None) -> list[dict]:
        A = []
        add = lambda key, sev, title, detail, cat: A.append({"key": key, "severity": sev, "title": title, "detail": detail, "category": cat})
        live, lv = self.live(), self.m.get("live", {})
        now = int(time.time())
        # Inverter faults
        f = (live.get("fault") or "").strip()
        if f and f.lower() not in ("no faults", "none", "normal", "0", "ok"):
            add("inverter_fault", "crit", "Inverter fault", f"The inverter reports: {f}.", "energy")
        # Solar yield
        y = self.yield_by_month(self.daily(366))
        if len(y) >= 3:
            best, last = max(v for _, v in y[:-1]), y[-1][1]
            if last < 0.6 * best:
                add("solar_yield", "crit", f"Solar output down {round((1 - last / best) * 100)}% for the same sunshine",
                    f"Yield fell from {best:.2f} to {last:.2f} kWh per MJ/m². Some seasonal drop is normal, but not this much. Check for dirt, shading or a string fault.", "energy")
        # String imbalance and drop-outs
        st = self.strings()["strings"]
        if len(st) >= 2 and all(s["kwh7"] > 1 for s in st):
            hi, lo = max(st, key=lambda s: s["kwh7"]), min(st, key=lambda s: s["kwh7"])
            if lo["kwh7"] < 0.7 * hi["kwh7"]:
                add("string_imbalance", "warn", f"{lo['name']} is {round((1 - lo['kwh7'] / hi['kwh7']) * 100)}% below {hi['name']}",
                    f"Last 7 days: {lo['kwh7']} kWh vs {hi['kwh7']} kWh. Check for shading, dirt or a loose connector.", "energy")
        if len(st) >= 2:
            for s in st:
                others = [o for o in st if o is not s]
                for d, on, off, pk, pw in s["ramps"][-3:]:
                    o = next((r for r in others[0]["ramps"] if r[0] == d), None)
                    if o and off < 13 * 60 and o[2] - off > 180:
                        add(f"string_dropout_{s['entity']}", "warn", f"{s['name']} cut out early on {d[8:]}/{d[5:7]}",
                            f"It stopped producing at {off // 60:02d}:{off % 60:02d} while {others[0]['name']} carried on until {o[2] // 60:02d}:{o[2] % 60:02d}. Check the isolator and connectors.", "energy")
                        break
        # Battery
        bt = lv.get("batt_temp")
        if bt:
            rows = self.db.series_full(bt, "hour", now - 7 * DAY)
            if rows:
                mean7 = float(np.mean([r["mean"] or 0 for r in rows]))
                max7 = max(r["max"] or 0 for r in rows)
                if mean7 > 45 or max7 > 60:
                    add("battery_hot", "warn", "Battery running hot",
                        f"Average {mean7:.0f} °C over the last week, peaks of {max7:.0f} °C. Lithium batteries age faster above 45 °C. Check the battery has airflow.", "energy")
        soh = live.get("soh")
        if soh and soh < 80:
            add("battery_soh", "warn", "Battery health below 80%", f"The battery reports {soh:.0f}% health. Capacity is noticeably reduced.", "energy")
        for t in self.m.get("sys_temps", []):
            if t == bt:
                continue
            rows = self.db.series_full(t, "hour", now - 7 * DAY)
            if rows and max(r["max"] or 0 for r in rows) > 85:
                name = (self.c.states.get(t) or {}).get("attributes", {}).get("friendly_name", t).replace("Luxpower Inverter", "Inverter").strip()
                add(f"hot_{t}", "warn", "Inverter running hot", f"{name} peaked at {max(r['max'] or 0 for r in rows):.0f} °C this week. Clean the fan inlets and check the vents.", "energy")
                break
        # Appliances
        for a in apps or self.appliance_health():
            if a["status"] in ("warn", "crit"):
                add(f"app_{a['id']}", a["status"], f"{a['name']}: {'stopped' if a['status'] == 'crit' else 'check soon'}", a["note"], "appliances")
        # Offline devices
        off = self.m.get("offline", [])
        if off:
            add("offline", "info", f"{len(off)} device{'s' if len(off) > 1 else ''} offline", ", ".join(off[:8]) + (f" and {len(off) - 8} more." if len(off) > 8 else "."), "house")
        # Low batteries
        low = []
        for b in self.m.get("batteries", []):
            v = self.num(b)
            if v is not None and v < 20:
                low.append(f"{(self.c.states[b]['attributes'].get('friendly_name') or b)} ({v:.0f}%)")
        if low:
            add("low_batteries", "warn", "Sensor batteries low", ", ".join(low), "house")
        # Always-on load
        base = self.habits()["base_kw"]
        pi, _ = self.prices()
        if base > 0.5:
            add("base_load", "info", f"Always-on load is {base * 1000:.0f} W", f"That's about {base * 24 * 30:.0f} kWh, R{base * 24 * 30 * pi:,.0f} a month, even when everyone's asleep.", "habits")
        return A
