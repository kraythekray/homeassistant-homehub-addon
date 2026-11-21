# Home Hub

## Getting started

Start the add-on and open **Home Hub** from the sidebar. On the first start it reads up to a year
of hourly history from Home Assistant's long-term statistics, so most charts are filled
straight away. The 5-minute solar string data starts with Home Assistant's last 10 days and builds
up from there.

Home Hub discovers your setup automatically:

- **Energy system:** the solar, battery and grid sensors from **Settings → Dashboards → Energy**.
  Live power, battery charge and inverter temperatures are matched from the same integration.
- **Appliances:** every device that has a power sensor in W or kW.
- **Controls:** lights, fans, and switches whose names look like lights, pumps, sprinklers or
  garden equipment. Fridge, freezer and kettle plugs are never shown as switches.

New devices appear within the hour.

## Options

| Option | Default | What it does |
|---|---|---|
| `weather_enabled` | `true` | Fetch weather from [Open-Meteo](https://open-meteo.com), a free service with no account needed. Your home's coordinates are rounded to 1 decimal place (about 11 km) before they're sent. |
| `backfill_days` | `365` | How much history to load the first time (30–1095). |
| `import_price` | from Energy settings | Price you pay per kWh. |
| `export_price` | from Energy settings | Price you're paid per kWh exported. When the two are equal, the plan knows that moving loads doesn't change the bill. |
| `battery_kwh` | from inverter | Usable battery capacity. It's worked out from the battery's Ah rating if left blank. |
| `panel_kwp` | estimated | Size of your solar array, used by the savings plan. |
| `notify_service` | none | A notify service such as `notify.mobile_app_my_phone`. You get a push notification when a high or medium alert is raised. |

## Alerts

Alerts are checked every 5 minutes and stored with the time they were first raised, last seen,
resolved and acknowledged. The built-in rules cover:

- inverter faults
- solar yield dropping well below your best month for the same sunshine
- one panel string producing much less than another, or cutting out early
- the battery or inverter running hot, and battery health below 80%
- appliances drawing more or less power than their own normal
- an always-on appliance (fridge, freezer) that has stopped drawing power
- devices that have gone offline, and low sensor batteries
- a high always-on load

## Data

Everything is stored in SQLite in the add-on's `/data` folder and included in Home Assistant
backups. Home Hub talks to Home Assistant through the Supervisor, so you don't need a token.
The only outside service it uses is Open-Meteo, if weather is enabled.

## Running outside Home Assistant

The same code runs standalone on any machine on your network:

```bash
cd home_hub
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
printf 'HA_URL=http://homeassistant.local:8123\nHA_TOKEN=<long-lived token>\n' > .env && chmod 600 .env
cd backend && ../.venv/bin/python -m homehub.main   # http://<machine>:8099
```

## API

`GET api/live`, `GET api/view/{overview|energy|appliances|habits|weather|plan}`, `GET api/alerts`,
`POST api/alerts/{key}/ack`, `POST api/control` (toggles only discovered controls), `POST api/refresh`.
