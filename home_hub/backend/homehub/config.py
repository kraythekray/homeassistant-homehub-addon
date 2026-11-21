"""Runtime configuration.

Works in two modes:
  * Standalone: HA_URL + HA_TOKEN (long-lived access token) from env or .env.
  * Home Assistant add-on: SUPERVISOR_TOKEN is injected and the API is reached
    through http://supervisor/core. Add-on options are read from /data/options.json.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


@dataclass
class Settings:
    ha_url: str
    ha_token: str
    addon: bool
    db_path: Path
    port: int = 8099
    weather_enabled: bool = True
    # Coordinates are rounded before being sent to the weather service (1 dp ~ 11 km).
    weather_precision: int = 1
    import_price: float | None = None   # R/kWh; None -> taken from HA energy settings
    export_price: float | None = None
    battery_kwh: float | None = None    # usable capacity override
    panel_kwp: float | None = None      # installed array size override
    notify_service: str = ""            # e.g. notify.mobile_app_phone, for high alerts
    backfill_days: int = 365
    extra: dict = field(default_factory=dict)


def load() -> Settings:
    _load_dotenv()
    sup = os.environ.get("SUPERVISOR_TOKEN")
    opts: dict = {}
    opt_file = Path("/data/options.json")
    if sup and opt_file.exists():
        opts = json.loads(opt_file.read_text())

    def opt(name: str, env: str, cast=str, default=None):
        v = opts.get(name)
        if v in (None, ""):
            v = os.environ.get(env)
        if v in (None, ""):
            return default
        try:
            return cast(v)
        except (TypeError, ValueError):
            return default

    if sup:
        url, token, addon = "http://supervisor/core", sup, True
        db = Path("/data/homehub.sqlite")
    else:
        url = os.environ.get("HA_URL", "").rstrip("/")
        token = os.environ.get("HA_TOKEN", "")
        addon = False
        db = Path(os.environ.get("HOMEHUB_DB", ROOT / "data" / "homehub.sqlite"))
    if not url or not token:
        raise SystemExit("Set HA_URL and HA_TOKEN (or run as a Home Assistant add-on).")
    db.parent.mkdir(parents=True, exist_ok=True)
    return Settings(
        ha_url=url,
        ha_token=token,
        addon=addon,
        db_path=db,
        port=opt("port", "HOMEHUB_PORT", int, 8099),
        weather_enabled=opt("weather_enabled", "HOMEHUB_WEATHER", lambda v: str(v).lower() not in ("0", "false", "no"), True),
        import_price=opt("import_price", "HOMEHUB_IMPORT_PRICE", float),
        export_price=opt("export_price", "HOMEHUB_EXPORT_PRICE", float),
        battery_kwh=opt("battery_kwh", "HOMEHUB_BATTERY_KWH", float),
        panel_kwp=opt("panel_kwp", "HOMEHUB_PANEL_KWP", float),
        notify_service=opt("notify_service", "HOMEHUB_NOTIFY", str, "") or "",
        backfill_days=opt("backfill_days", "HOMEHUB_BACKFILL_DAYS", int, 365),
    )
