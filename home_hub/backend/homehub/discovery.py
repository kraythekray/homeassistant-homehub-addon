"""Build a model of the home from Home Assistant's registries, states and energy settings.

Nothing here is hard-coded to one house: the solar/battery/grid wiring comes from the
Energy dashboard settings, appliances are any devices with a power meter, and controls
are the lights, fans and switches the family would actually toggle.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

PHONE_PLATFORMS = {"mobile_app"}
SKIP_DOMAINS_CTRL = set()
CONTROL_WORDS = re.compile(r"light|lamp|fan|pump|sprinkler|lawn|garden|pool|heater|geyser|tv|gate|garage door|irrigation|bed|spray", re.I)
GARDEN_WORDS = re.compile(r"sprinkler|lawn|garden|pool|pump|irrigation|spray|bedding", re.I)
ALWAYS_ON_WORDS = re.compile(r"fridge|freezer|router|deco|nvr|server|alarm|camera", re.I)


def _pretty(s: str) -> str:
    return s.replace("_", " ").strip().capitalize()


def _clean_name(n: str) -> str:
    n = re.sub(r"\s+", " ", n or "").strip()
    return re.sub(r"\s+(power|socket\s*\d*|switch|energy.*)$", "", n, flags=re.I).strip() or n


def build_model(states: list[dict], ents: list[dict], devs: list[dict], areas: list[dict], prefs: dict, cfg: dict) -> dict[str, Any]:
    st = {s["entity_id"]: s for s in states}
    reg = {e["entity_id"]: e for e in ents}
    dev = {d["id"]: d for d in devs}
    area_name = {a["area_id"]: a["name"] for a in areas}

    def attr(eid, k, d=None):
        return (st.get(eid) or {}).get("attributes", {}).get(k, d)

    def fname(eid):
        return attr(eid, "friendly_name") or eid.split(".", 1)[1]

    def device_of(eid):
        r = reg.get(eid)
        return dev.get(r["device_id"]) if r and r.get("device_id") else None

    def dname(d):
        n = (d.get("name_by_user") or d.get("name") or "").strip() if d else ""
        return re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", n, flags=re.I)

    def area_of(eid):
        r = reg.get(eid) or {}
        aid = r.get("area_id") or (device_of(eid) or {}).get("area_id")
        return area_name.get(aid) or (_pretty(aid) if aid else None)

    def visible(eid):
        r = reg.get(eid)
        return not (r and (r.get("hidden_by") or r.get("disabled_by") or r.get("entity_category")))

    # ---------------- energy system (from the Energy dashboard settings) ----------------
    energy = {"solar": [], "battery": None, "grid": None, "devices": [], "import_price": None, "export_price": None}
    for src in prefs.get("energy_sources", []):
        t = src.get("type")
        if t == "solar":
            energy["solar"].append({"energy": src.get("stat_energy_from"), "power": src.get("stat_rate")})
        elif t == "battery":
            energy["battery"] = {"from": src.get("stat_energy_from"), "to": src.get("stat_energy_to")}
        elif t == "grid":
            # older HA: flow_from/flow_to lists; newer: flat keys
            f = src.get("stat_energy_from") or (src.get("flow_from") or [{}])[0].get("stat_energy_from")
            to = src.get("stat_energy_to") or (src.get("flow_to") or [{}])[0].get("stat_energy_to")
            energy["grid"] = {"from": f, "to": to}
            energy["import_price"] = src.get("number_energy_price") or (src.get("flow_from") or [{}])[0].get("number_energy_price")
            energy["export_price"] = src.get("number_energy_price_export") or (src.get("flow_to") or [{}])[0].get("number_energy_price")
    energy["devices"] = [d["stat_consumption"] for d in prefs.get("device_consumption", []) if d.get("stat_consumption")]

    # The platform(s) behind the energy system: their entities are not "appliances".
    sys_ids = [x["energy"] for x in energy["solar"]] + [v for k, v in (energy["grid"] or {}).items()] + [v for v in (energy["battery"] or {}).values()]
    sys_platforms = {reg[e]["platform"] for e in sys_ids if e and e in reg}
    sys_entities = [e for e, r in reg.items() if r.get("platform") in sys_platforms]

    def find_sys(*patterns, dc=None, unit=None):
        for p in patterns:
            rx = re.compile(p)
            for e in sys_entities:
                if not e.startswith("sensor.") or not rx.search(e):
                    continue
                if dc and attr(e, "device_class") != dc:
                    continue
                if unit and attr(e, "unit_of_measurement") != unit:
                    continue
                return e
        return None

    live = {
        "solar_power": [x["power"] for x in energy["solar"] if x.get("power")] or [find_sys(r"pv_?power$", r"solar.*power", dc="power")],
        "grid_import": find_sys(r"power_from_grid$", r"grid.*import.*power", r"grid_power$", dc="power"),
        "grid_export": find_sys(r"power_to_grid$", r"grid.*export.*power", dc="power"),
        "batt_charge": find_sys(r"battery_charge_power$", dc="power"),
        "batt_discharge": find_sys(r"battery_discharge_power$", dc="power"),
        "batt_soc": find_sys(r"battery_soc$", r"state_of_charge", r"_soc$"),
        "batt_soh": find_sys(r"battery_soh$", r"state_of_health"),
        "load": find_sys(r"(?<!smart_)load_power$", r"home.*power", r"consumption.*power", dc="power"),
        "batt_temp": find_sys(r"battery_temperature$", dc="temperature"),
        "batt_capacity_ah": find_sys(r"battery_capacity$"),
        "batt_voltage": find_sys(r"battery_voltage$", dc="voltage"),
        "fault": find_sys(r"active_fault_text$", r"fault"),
        "warning": find_sys(r"active_warning_text$"),
        "inverter_state": find_sys(r"inverter_state$"),
        "grid_voltage": find_sys(r"grid_voltage$", dc="voltage"),
        "grid_frequency": find_sys(r"grid_frequency$", dc="frequency"),
        "pv_total": find_sys(r"pv_energy_total$", r"solar.*total"),
        "forecast_today": next((e for e in st if e.startswith("sensor.energy_production_today") and not e.endswith("remaining")), None),
        "forecast_tomorrow": "sensor.energy_production_tomorrow" if "sensor.energy_production_tomorrow" in st else None,
        "co2": next((e for e in st if e.startswith("sensor.") and "co2_intensity" in e), None),
    }
    # Temperatures on the energy system, for heat alerts.
    sys_temps = [e for e in sys_entities if e.startswith("sensor.") and attr(e, "device_class") == "temperature"]

    # ---------------- appliances: devices with a power meter ----------------
    by_dev = defaultdict(list)
    for e in st:
        r = reg.get(e)
        if r and r.get("device_id"):
            by_dev[r["device_id"]].append(e)
    appliances = []
    for did, eids in by_dev.items():
        d = dev.get(did)
        if not d or d.get("disabled_by") or d.get("entry_type") == "service":
            continue
        plats = {reg[e]["platform"] for e in eids}
        if plats & (sys_platforms | PHONE_PLATFORMS):
            continue
        power = [e for e in eids if e.startswith("sensor.") and attr(e, "device_class") == "power" and attr(e, "unit_of_measurement") in ("W", "kW")]
        if not power:
            continue
        energy_s = [e for e in eids if e.startswith("sensor.") and attr(e, "device_class") == "energy" and attr(e, "state_class") in ("total", "total_increasing")]
        sw = [e for e in eids if e.startswith("switch.") and visible(e)]
        name = dname(d) or _clean_name(fname(power[0]))
        appliances.append({
            "id": power[0].split(".", 1)[1],
            "name": name,
            "power": power[0],
            "energy": next((e for e in energy_s if e in energy["devices"]), energy_s[0] if energy_s else None),
            "switch": sw[0] if sw else None,
            "area": area_of(power[0]),
            "always_on": bool(ALWAYS_ON_WORDS.search(name)),
            "available": (st[power[0]]["state"] not in ("unavailable", "unknown")),
        })
    appliances.sort(key=lambda a: a["name"].lower())

    # ---------------- controls ----------------
    controls, seen = [], set()
    appliance_switches = {a["switch"] for a in appliances if a["switch"]}
    for e, s in st.items():
        dom = e.split(".", 1)[0]
        if dom not in ("light", "switch", "fan") or not visible(e):
            continue
        r = reg.get(e) or {}
        if r.get("platform") in sys_platforms | PHONE_PLATFORMS:
            continue
        name = _clean_name(fname(e))
        if dom == "switch":
            dc = attr(e, "device_class")
            if e in appliance_switches and not CONTROL_WORDS.search(name):
                continue  # don't hand the family a kettle/fridge kill switch
            if dc == "outlet" and not CONTROL_WORDS.search(name):
                continue
            if not CONTROL_WORDS.search(name) and r.get("platform") not in ("rainbird",):
                continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        group = "Garden & pool" if GARDEN_WORDS.search(name) or r.get("platform") == "rainbird" else ("Lights & fans" if dom in ("light", "fan") or re.search(r"light|lamp|fan", name, re.I) else "Other")
        controls.append({"entity_id": e, "name": name, "group": group, "area": area_of(e)})
    controls.sort(key=lambda c: (c["group"], c["name"].lower()))

    # ---------------- around the house ----------------
    house = {
        "alarms": [e for e in st if e.startswith("alarm_control_panel.") and visible(e)],
        "cameras": [e for e in st if e.startswith("camera.") and visible(e)],
        "persons": [e for e in st if e.startswith("person.")],
        "calendars": [e for e in st if e.startswith("calendar.") and re.search(r"garbage|bin|refuse|waste|recycl", e)],
        "loadshedding": next((e for e in st if re.match(r"sensor\.loadshedding_.*local.*status|sensor\.loadshedding_.*area.*stage", e)), None),
        "loadshedding_calendar": next((e for e in st if e.startswith("calendar.loadshedding") and "schedule" in e), None),
        "rain_sensor": next((e for e in st if e.startswith("binary_sensor.") and "rain" in e), None),
        "doors": [e for e in st if e.startswith("binary_sensor.") and attr(e, "device_class") in ("door", "window", "garage_door") and visible(e)],
    }

    # Low batteries on household sensors (not phones).
    batteries = []
    for e, s in st.items():
        if attr(e, "device_class") == "battery" and attr(e, "unit_of_measurement") == "%" and (reg.get(e) or {}).get("platform") not in PHONE_PLATFORMS | sys_platforms:
            batteries.append(e)

    # Devices that have stopped reporting: a device whose user-facing entities are all unavailable.
    offline = []
    for did, eids in by_dev.items():
        d = dev.get(did)
        if not d or d.get("disabled_by") or ({reg[e]["platform"] for e in eids} & PHONE_PLATFORMS):
            continue
        main = [e for e in eids if e.split(".")[0] in ("switch", "light", "fan", "sensor", "camera", "binary_sensor") and not (reg[e].get("entity_category"))]
        if main and all(st[e]["state"] == "unavailable" for e in main):
            offline.append(dname(d) or _clean_name(fname(main[0])))

    lat, lon = cfg.get("latitude"), cfg.get("longitude")
    return {
        "location": {"name": cfg.get("location_name"), "lat": lat, "lon": lon, "tz": cfg.get("time_zone"), "currency": cfg.get("currency", "ZAR")},
        "energy": energy,
        "live": live,
        "sys_temps": sys_temps,
        "appliances": appliances,
        "controls": controls,
        "house": house,
        "batteries": batteries,
        "offline": sorted(set(offline)),
        "counts": {"entities": len(states), "appliances": len(appliances), "controls": len(controls)},
    }
