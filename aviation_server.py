"""
AviationStack MCP Server
========================
A FastMCP server exposing AviationStack API endpoints as MCP tools,
with Custom HTML App UIs for data-rich responses.

Transport: HTTP (Railway-ready)
Author: 360 Automation
"""

import json
import os
from typing import Annotated

import httpx
from fastmcp import FastMCP, Context
from fastmcp.server.apps import AppConfig, ResourceCSP
from fastmcp.server.lifespan import lifespan
from fastmcp.tools.tool import ToolResult
from starlette.requests import Request
from starlette.responses import JSONResponse

# ─── Lifespan: initialise shared HTTP client + validate API key ───────────────

@lifespan
async def app_lifespan(server):
    api_key = os.environ.get("AVIATIONSTACK_API_KEY")
    if not api_key:
        raise RuntimeError("AVIATIONSTACK_API_KEY environment variable is not set.")

    async with httpx.AsyncClient(
        base_url="http://api.aviationstack.com/v1",
        timeout=15.0,
    ) as http:
        yield {"http": http, "api_key": api_key}


# ─── Server ───────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="AviationStack MCP",
    instructions=(
        "Access real-time, historical, and scheduled aviation data via AviationStack. "
        "Use flight_board for a visual departures/arrivals UI. "
        "Use the lookup tools for airports, airlines, airplanes, routes, and countries."
    ),
    lifespan=app_lifespan,
    version="1.0.0",
)


# ─── Internal helpers ─────────────────────────────────────────────────────────

async def _get(ctx: Context, endpoint: str, params: dict) -> dict:
    http: httpx.AsyncClient = ctx.lifespan_context["http"]
    api_key: str = ctx.lifespan_context["api_key"]
    params["access_key"] = api_key
    # Remove None values
    params = {k: v for k, v in params.items() if v is not None}
    response = await http.get(endpoint, params=params)
    response.raise_for_status()
    return response.json()


# ══════════════════════════════════════════════════════════════════════════════
# TOOLS
# ══════════════════════════════════════════════════════════════════════════════

# ─── 1. Real-time / Historical Flights ────────────────────────────────────────

VIEW_FLIGHTS = "ui://aviation/flights-board.html"

@mcp.tool(
    name="get_flights",
    description=(
        "Retrieve real-time or historical flight data. "
        "Filter by flight number, IATA codes, airline, or date. "
        "Omit flight_date for live data (Free plan). "
        "Provide flight_date (YYYY-MM-DD) for historical data (Basic+ plan)."
    ),
    annotations={"readOnlyHint": True, "openWorldHint": True},
    app=AppConfig(resource_uri=VIEW_FLIGHTS),
)
async def get_flights(
    ctx: Context,
    flight_iata: Annotated[str | None, "IATA flight number, e.g. 'AA101'"] = None,
    dep_iata: Annotated[str | None, "Departure airport IATA code, e.g. 'LOS'"] = None,
    arr_iata: Annotated[str | None, "Arrival airport IATA code, e.g. 'LHR'"] = None,
    airline_iata: Annotated[str | None, "Airline IATA code, e.g. 'AA'"] = None,
    flight_status: Annotated[
        str | None,
        "Filter by status: 'scheduled', 'active', 'landed', 'cancelled', 'incident', 'diverted'"
    ] = None,
    flight_date: Annotated[str | None, "Historical date in YYYY-MM-DD format"] = None,
    limit: Annotated[int, "Max results to return (1-100)"] = 20,
) -> ToolResult:
    data = await _get(ctx, "/flights", {
        "flight_iata": flight_iata,
        "dep_iata": dep_iata,
        "arr_iata": arr_iata,
        "airline_iata": airline_iata,
        "flight_status": flight_status,
        "flight_date": flight_date,
        "limit": limit,
    })
    flights = data.get("data", [])
    summary = (
        f"Found {len(flights)} flight(s)"
        + (f" departing {dep_iata}" if dep_iata else "")
        + (f" arriving {arr_iata}" if arr_iata else "")
        + (f" on {flight_date}" if flight_date else " (live)")
        + "."
    )
    return ToolResult(
        content=summary,
        structured_content={"flights": flights, "total": len(flights)},
    )


# ─── 2. Flight Schedules ──────────────────────────────────────────────────────

VIEW_SCHEDULES = "ui://aviation/schedules-board.html"

@mcp.tool(
    name="get_flight_schedules",
    description=(
        "Retrieve scheduled (future) flight data. Requires Basic plan or above. "
        "Filter by departure/arrival airport, date range, or airline."
    ),
    annotations={"readOnlyHint": True, "openWorldHint": True},
    app=AppConfig(resource_uri=VIEW_SCHEDULES),
)
async def get_flight_schedules(
    ctx: Context,
    dep_iata: Annotated[str | None, "Departure airport IATA code"] = None,
    arr_iata: Annotated[str | None, "Arrival airport IATA code"] = None,
    airline_iata: Annotated[str | None, "Airline IATA code"] = None,
    date: Annotated[str | None, "Scheduled date YYYY-MM-DD"] = None,
    limit: Annotated[int, "Max results (1-100)"] = 20,
) -> ToolResult:
    data = await _get(ctx, "/flight_schedules", {
        "dep_iata": dep_iata,
        "arr_iata": arr_iata,
        "airline_iata": airline_iata,
        "date": date,
        "limit": limit,
    })
    schedules = data.get("data", [])
    return ToolResult(
        content=f"Found {len(schedules)} scheduled flight(s).",
        structured_content={"schedules": schedules, "total": len(schedules)},
    )


# ─── 3. Airport Lookup ────────────────────────────────────────────────────────

VIEW_AIRPORTS = "ui://aviation/airports-table.html"

@mcp.tool(
    name="get_airports",
    description="Search airports by name, IATA code, country, or city.",
    annotations={"readOnlyHint": True, "openWorldHint": True},
    app=AppConfig(resource_uri=VIEW_AIRPORTS),
)
async def get_airports(
    ctx: Context,
    search: Annotated[str | None, "Free-text search (airport name or city)"] = None,
    iata_code: Annotated[str | None, "3-letter IATA airport code"] = None,
    country_iso2: Annotated[str | None, "2-letter country ISO code, e.g. 'NG'"] = None,
    limit: Annotated[int, "Max results (1-100)"] = 20,
) -> ToolResult:
    data = await _get(ctx, "/airports", {
        "search": search,
        "iata_code": iata_code,
        "country_iso2": country_iso2,
        "limit": limit,
    })
    airports = data.get("data", [])
    return ToolResult(
        content=f"Found {len(airports)} airport(s).",
        structured_content={"airports": airports, "total": len(airports)},
    )


# ─── 4. Airline Lookup ────────────────────────────────────────────────────────

VIEW_AIRLINES = "ui://aviation/airlines-table.html"

@mcp.tool(
    name="get_airlines",
    description="Look up airlines by name, IATA code, or country.",
    annotations={"readOnlyHint": True, "openWorldHint": True},
    app=AppConfig(resource_uri=VIEW_AIRLINES),
)
async def get_airlines(
    ctx: Context,
    search: Annotated[str | None, "Free-text search (airline name)"] = None,
    iata_code: Annotated[str | None, "2-letter airline IATA code, e.g. 'LH'"] = None,
    country_iso2: Annotated[str | None, "2-letter country ISO code"] = None,
    limit: Annotated[int, "Max results (1-100)"] = 20,
) -> ToolResult:
    data = await _get(ctx, "/airlines", {
        "search": search,
        "iata_code": iata_code,
        "country_iso2": country_iso2,
        "limit": limit,
    })
    airlines = data.get("data", [])
    return ToolResult(
        content=f"Found {len(airlines)} airline(s).",
        structured_content={"airlines": airlines, "total": len(airlines)},
    )


# ─── 5. Airplane / Aircraft Lookup ────────────────────────────────────────────

VIEW_AIRPLANES = "ui://aviation/airplanes-table.html"

@mcp.tool(
    name="get_airplanes",
    description="Look up registered aircraft by registration number, IATA type, or airline.",
    annotations={"readOnlyHint": True, "openWorldHint": True},
    app=AppConfig(resource_uri=VIEW_AIRPLANES),
)
async def get_airplanes(
    ctx: Context,
    search: Annotated[str | None, "Free-text search"] = None,
    registration_number: Annotated[str | None, "Aircraft registration, e.g. 'N12345'"] = None,
    iata_type: Annotated[str | None, "IATA aircraft type code, e.g. '73H'"] = None,
    airline_iata: Annotated[str | None, "Airline IATA code to filter by"] = None,
    limit: Annotated[int, "Max results (1-100)"] = 20,
) -> ToolResult:
    data = await _get(ctx, "/airplanes", {
        "search": search,
        "registration_number": registration_number,
        "iata_type": iata_type,
        "airline_iata": airline_iata,
        "limit": limit,
    })
    airplanes = data.get("data", [])
    return ToolResult(
        content=f"Found {len(airplanes)} aircraft registration(s).",
        structured_content={"airplanes": airplanes, "total": len(airplanes)},
    )


# ─── 6. Routes ────────────────────────────────────────────────────────────────

VIEW_ROUTES = "ui://aviation/routes-table.html"

@mcp.tool(
    name="get_routes",
    description=(
        "Retrieve airline route metadata — which airlines fly between two airports. "
        "Requires Basic plan or above."
    ),
    annotations={"readOnlyHint": True, "openWorldHint": True},
    app=AppConfig(resource_uri=VIEW_ROUTES),
)
async def get_routes(
    ctx: Context,
    dep_iata: Annotated[str | None, "Departure airport IATA code"] = None,
    arr_iata: Annotated[str | None, "Arrival airport IATA code"] = None,
    airline_iata: Annotated[str | None, "Airline IATA code"] = None,
    flight_number: Annotated[str | None, "Specific flight number"] = None,
    limit: Annotated[int, "Max results (1-100)"] = 20,
) -> ToolResult:
    data = await _get(ctx, "/routes", {
        "dep_iata": dep_iata,
        "arr_iata": arr_iata,
        "airline_iata": airline_iata,
        "flight_number": flight_number,
        "limit": limit,
    })
    routes = data.get("data", [])
    return ToolResult(
        content=f"Found {len(routes)} route(s).",
        structured_content={"routes": routes, "total": len(routes)},
    )


# ══════════════════════════════════════════════════════════════════════════════
# APP RESOURCES — HTML UI for each tool
# Each resource is linked to a tool via AppConfig(resource_uri=...)
# ══════════════════════════════════════════════════════════════════════════════

CDN = "https://unpkg.com"
EXT_APPS_CDN = f"{CDN}/@modelcontextprotocol/ext-apps@0.4.0/app-with-deps"

# ─── Shared CSS / JS snippets ─────────────────────────────────────────────────

SHARED_STYLES = """
  <meta name="color-scheme" content="dark">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap');

    :root {
      --bg: #080d13;
      --panel: #0d1520;
      --border: #0d2035;
      --accent: #00CCFF;
      --navy: #003262;
      --text: #e2e8f0;
      --muted: #64748b;
      --green: #22c55e;
      --yellow: #f59e0b;
      --red: #ef4444;
      --glow: rgba(0,204,255,0.18);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: 'JetBrains Mono', monospace;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      padding: 16px;
    }

    .header {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--border);
    }

    .header h1 {
      font-size: 13px;
      font-weight: 700;
      color: var(--accent);
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }

    .badge {
      font-size: 10px;
      padding: 2px 8px;
      border-radius: 3px;
      background: var(--navy);
      color: var(--accent);
      border: 1px solid var(--border);
      font-weight: 600;
    }

    .count-badge {
      background: var(--panel);
      border: 1px solid var(--accent);
      color: var(--accent);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 11px;
    }

    thead th {
      text-align: left;
      padding: 8px 10px;
      color: var(--accent);
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      border-bottom: 1px solid var(--border);
      font-weight: 700;
    }

    tbody tr {
      border-bottom: 1px solid var(--border);
      transition: background 0.15s;
    }

    tbody tr:hover { background: rgba(0,204,255,0.04); }

    td {
      padding: 9px 10px;
      color: var(--text);
      vertical-align: middle;
    }

    .status {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 8px;
      border-radius: 3px;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .status-active    { background: rgba(34,197,94,0.12);  color: var(--green);  border: 1px solid rgba(34,197,94,0.3); }
    .status-scheduled { background: rgba(0,204,255,0.1);   color: var(--accent); border: 1px solid rgba(0,204,255,0.25); }
    .status-landed    { background: rgba(100,116,139,0.15); color: var(--muted);  border: 1px solid var(--border); }
    .status-cancelled { background: rgba(239,68,68,0.12);  color: var(--red);    border: 1px solid rgba(239,68,68,0.3); }
    .status-diverted  { background: rgba(245,158,11,0.12); color: var(--yellow); border: 1px solid rgba(245,158,11,0.3); }
    .status-incident  { background: rgba(239,68,68,0.2);   color: var(--red);    border: 1px solid var(--red); }

    .dot {
      width: 6px; height: 6px;
      border-radius: 50%;
      display: inline-block;
    }
    .dot-green  { background: var(--green); box-shadow: 0 0 4px var(--green); }
    .dot-cyan   { background: var(--accent); }
    .dot-grey   { background: var(--muted); }
    .dot-red    { background: var(--red); }
    .dot-yellow { background: var(--yellow); }

    .route-arrow {
      color: var(--accent);
      font-size: 12px;
      margin: 0 4px;
    }

    .dim   { color: var(--muted); font-size: 10px; }
    .mono  { font-family: 'JetBrains Mono', monospace; }
    .bold  { font-weight: 700; }
    .cyan  { color: var(--accent); }

    .empty-state {
      text-align: center;
      padding: 40px;
      color: var(--muted);
      font-size: 12px;
    }

    .scan-line {
      border-top: 1px solid var(--border);
      padding-top: 10px;
      margin-top: 10px;
      font-size: 10px;
      color: var(--muted);
      display: flex;
      justify-content: space-between;
    }

    .loader {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 40px;
      color: var(--accent);
      font-size: 11px;
    }

    .spinner {
      width: 14px; height: 14px;
      border: 2px solid var(--border);
      border-top-color: var(--accent);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }

    @keyframes spin { to { transform: rotate(360deg); } }

    .card-glow {
      border-top: 1px solid var(--accent);
      box-shadow: 0 -2px 12px var(--glow);
      background: var(--panel);
      border-radius: 6px;
      padding: 14px;
      margin-bottom: 10px;
    }

    .footer {
      margin-top: 16px;
      font-size: 9px;
      color: var(--muted);
      text-align: right;
      letter-spacing: 0.06em;
    }
  </style>
"""

SHARED_CONNECT_JS = f"""
  <script type="module" id="mcp-bootstrap">
    import {{ App }} from "{EXT_APPS_CDN}";
    const app = new App({{ name: "AviationStack UI", version: "1.0.0" }});
    window.__mcpApp = app;
app.ontoolresult = (result) => {{
      const sc = result?.structuredContent
               ?? result?.result?.structuredContent
               ?? null;
      const content = result?.content ?? result?.result?.content ?? [];
      if (sc && window.__onData) {{ window.__onData(sc); return; }}
      for (const block of (Array.isArray(content) ? content : [])) {{
        if (block?.type === 'text' && block?.text) {{
          try {{ const d = JSON.parse(block.text); if (window.__onData) {{ window.__onData(d); return; }} }} catch(e) {{}}
        }}
      }}
      console.log('ontoolresult payload:', JSON.stringify(result, null, 2));
    }};
    await app.connect();
    document.getElementById('loading')?.remove();
  </script>
"""


def _html_shell(title: str, icon: str, body_js: str, extra_csp_domains: list[str] | None = None) -> str:
    """Wrap content in the shared terminal shell."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
  {SHARED_STYLES}
</head>
<body>
  <div class="header">
    <span style="font-size:18px">{icon}</span>
    <h1>{title}</h1>
    <span class="badge" id="count-badge"></span>
  </div>

  <div id="loading" class="loader">
    <div class="spinner"></div>
    Waiting for data...
  </div>

  <div id="content" style="display:none"></div>

  <div class="footer">David Oratokhai // 360 Automation // AviationStack MCP v1.0</div>

  <script>
{body_js}
  </script>
  {SHARED_CONNECT_JS}
</body>
</html>"""


# ─── Flights Board UI ─────────────────────────────────────────────────────────

FLIGHTS_BOARD_JS = """
function statusClass(s) {
  const m = { active:'active', scheduled:'scheduled', landed:'landed',
               cancelled:'cancelled', diverted:'diverted', incident:'incident' };
  return 'status status-' + (m[s?.toLowerCase()] || 'scheduled');
}
function dotClass(s) {
  const m = { active:'green', scheduled:'cyan', landed:'grey', cancelled:'red',
               diverted:'yellow', incident:'red' };
  return 'dot dot-' + (m[s?.toLowerCase()] || 'grey');
}
function fmt(t) { return t ? t.substring(11,16) : '—'; }
function safe(v) { return v || '—'; }

window.__onData = function(d) {
  const flights = d.flights || d.data || [];
  const badge = document.getElementById('count-badge');
  if (badge) { badge.textContent = flights.length + ' flights'; badge.className = 'badge count-badge'; }

  const content = document.getElementById('content');
  content.style.display = '';
  document.getElementById('loading')?.remove();˙

  if (!flights.length) {
    content.innerHTML = '<div class="empty-state">⚠ No flights found for the given parameters.</div>';
    return;
  }

  const rows = flights.map(f => {
    const dep = f.departure || {};
    const arr = f.arrival || {};
    const fl  = f.flight   || {};
    const al  = f.airline  || {};
    const s   = f.flight_status || 'unknown';
    const delay = dep.delay ? `<span style="color:var(--yellow)">+${dep.delay}m</span>` : '<span class="dim">on time</span>';
    return `<tr>
      <td><span class="bold cyan">${safe(fl.iata)}</span><br><span class="dim">${safe(al.name)}</span></td>
      <td><span class="bold">${safe(dep.iata)}</span><br><span class="dim">${safe(dep.airport)?.substring(0,22)}</span></td>
      <td class="route-arrow">→</td>
      <td><span class="bold">${safe(arr.iata)}</span><br><span class="dim">${safe(arr.airport)?.substring(0,22)}</span></td>
      <td>${fmt(dep.scheduled)}<br><span class="dim">sched</span></td>
      <td>${fmt(dep.actual || dep.estimated)}<br><span class="dim">actual</span></td>
      <td>${delay}</td>
      <td><span class="${statusClass(s)}"><span class="${dotClass(s)}"></span>${s}</span></td>
    </tr>`;
  }).join('');

  content.innerHTML = `
    <table>
      <thead><tr>
        <th>Flight</th><th>From</th><th></th><th>To</th>
        <th>Sched Dep</th><th>Actual Dep</th><th>Delay</th><th>Status</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div class="scan-line">
      <span>AviationStack // Real-time Data</span>
      <span id="ts"></span>
    </div>`;
  document.getElementById('ts').textContent = new Date().toUTCString();
};
"""

@mcp.resource(
    VIEW_FLIGHTS,
    app=AppConfig(csp=ResourceCSP(resource_domains=[CDN, "https://fonts.googleapis.com", "https://fonts.gstatic.com"])),
)
def flights_board_ui() -> str:
    """Live flight board — departures, arrivals, status."""
    return _html_shell("Live Flight Board", "✈", FLIGHTS_BOARD_JS)


# ─── Schedules Board UI ───────────────────────────────────────────────────────

SCHEDULES_BOARD_JS = """
function fmt(t) { return t ? t.substring(0,16).replace('T',' ') : '—'; }
function safe(v) { return v || '—'; }

window.__onData = function(d) {
  const items = d.schedules || d.data || [];
  const badge = document.getElementById('count-badge');
  if (badge) { badge.textContent = items.length + ' schedules'; badge.className = 'badge count-badge'; }

  const content = document.getElementById('content');
  content.style.display = '';
  document.getElementById('loading')?.remove();

  if (!items.length) {
    content.innerHTML = '<div class="empty-state">⚠ No schedules found.</div>';
    return;
  }

  const rows = items.map(s => {
    const dep = s.departure || {};
    const arr = s.arrival   || {};
    const fl  = s.flight    || {};
    const al  = s.airline   || {};
    return `<tr>
      <td><span class="bold cyan">${safe(fl.iata)}</span><br><span class="dim">${safe(al.name)}</span></td>
      <td><span class="bold">${safe(dep.iata)}</span></td>
      <td class="route-arrow">→</td>
      <td><span class="bold">${safe(arr.iata)}</span></td>
      <td>${fmt(dep.scheduled)}</td>
      <td>${fmt(arr.scheduled)}</td>
      <td><span class="dim">${safe(s.aircraft?.icao)}</span></td>
    </tr>`;
  }).join('');

  content.innerHTML = `
    <table>
      <thead><tr>
        <th>Flight</th><th>From</th><th></th><th>To</th>
        <th>Dep (UTC)</th><th>Arr (UTC)</th><th>Aircraft</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div class="scan-line"><span>AviationStack // Scheduled Flights</span></div>`;
};
"""

@mcp.resource(
    VIEW_SCHEDULES,
    app=AppConfig(csp=ResourceCSP(resource_domains=[CDN, "https://fonts.googleapis.com", "https://fonts.gstatic.com"])),
)
def schedules_board_ui() -> str:
    """Scheduled flights board."""
    return _html_shell("Flight Schedules", "🗓", SCHEDULES_BOARD_JS)


# ─── Airports Table UI ────────────────────────────────────────────────────────

AIRPORTS_TABLE_JS = """
function safe(v) { return v || '—'; }

window.__onData = function(d) {
  const items = d.airports || d.data || [];
  const badge = document.getElementById('count-badge');
  if (badge) { badge.textContent = items.length + ' airports'; badge.className = 'badge count-badge'; }

  const content = document.getElementById('content');
  content.style.display = '';
  document.getElementById('loading')?.remove();

  if (!items.length) {
    content.innerHTML = '<div class="empty-state">⚠ No airports found.</div>';
    return;
  }

  const rows = items.map(a => `<tr>
    <td><span class="bold cyan">${safe(a.iata_code)}</span></td>
    <td><span class="bold">${safe(a.airport_name)}</span></td>
    <td>${safe(a.city_iata_code)} — ${safe(a.city?.city_name || a.city)}</td>
    <td>${safe(a.country_name)}</td>
    <td class="dim">${safe(a.latitude)}, ${safe(a.longitude)}</td>
    <td class="dim">${safe(a.timezone)}</td>
  </tr>`).join('');

  content.innerHTML = `
    <table>
      <thead><tr>
        <th>IATA</th><th>Airport Name</th><th>City</th>
        <th>Country</th><th>Coordinates</th><th>Timezone</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
};
"""

@mcp.resource(
    VIEW_AIRPORTS,
    app=AppConfig(csp=ResourceCSP(resource_domains=[CDN, "https://fonts.googleapis.com", "https://fonts.gstatic.com"])),
)
def airports_table_ui() -> str:
    """Airport lookup results."""
    return _html_shell("Airport Lookup", "🛬", AIRPORTS_TABLE_JS)


# ─── Airlines Table UI ────────────────────────────────────────────────────────

AIRLINES_TABLE_JS = """
function safe(v) { return v || '—'; }
function statusBadge(active) {
  return active === 1
    ? '<span class="status status-active"><span class="dot dot-green"></span>Active</span>'
    : '<span class="status status-landed">Inactive</span>';
}

window.__onData = function(d) {
  const items = d.airlines || d.data || [];
  const badge = document.getElementById('count-badge');
  if (badge) { badge.textContent = items.length + ' airlines'; badge.className = 'badge count-badge'; }

  const content = document.getElementById('content');
  content.style.display = '';
  document.getElementById('loading')?.remove();

  if (!items.length) {
    content.innerHTML = '<div class="empty-state">⚠ No airlines found.</div>';
    return;
  }

  const rows = items.map(a => `<tr>
    <td><span class="bold cyan">${safe(a.iata_code)}</span></td>
    <td><span class="bold">${safe(a.airline_name)}</span></td>
    <td>${safe(a.country_name)}</td>
    <td class="dim">${safe(a.hub_code)}</td>
    <td>${statusBadge(a.status === 'active' ? 1 : 0)}</td>
    <td class="dim" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
      ${safe(a.fleet_size) !== '—' ? safe(a.fleet_size) + ' aircraft' : '—'}
    </td>
  </tr>`).join('');

  content.innerHTML = `
    <table>
      <thead><tr>
        <th>IATA</th><th>Airline</th><th>Country</th>
        <th>Hub</th><th>Status</th><th>Fleet</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
};
"""

@mcp.resource(
    VIEW_AIRLINES,
    app=AppConfig(csp=ResourceCSP(resource_domains=[CDN, "https://fonts.googleapis.com", "https://fonts.gstatic.com"])),
)
def airlines_table_ui() -> str:
    """Airline lookup results."""
    return _html_shell("Airline Lookup", "🏢", AIRLINES_TABLE_JS)


# ─── Airplanes Table UI ───────────────────────────────────────────────────────

AIRPLANES_TABLE_JS = """
function safe(v) { return v || '—'; }

window.__onData = function(d) {
  const items = d.airplanes || d.data || [];
  const badge = document.getElementById('count-badge');
  if (badge) { badge.textContent = items.length + ' aircraft'; badge.className = 'badge count-badge'; }

  const content = document.getElementById('content');
  content.style.display = '';
  document.getElementById('loading')?.remove();

  if (!items.length) {
    content.innerHTML = '<div class="empty-state">⚠ No aircraft found.</div>';
    return;
  }

  const rows = items.map(a => `<tr>
    <td><span class="bold cyan">${safe(a.registration_number)}</span></td>
    <td>${safe(a.iata_type)}</td>
    <td><span class="bold">${safe(a.airline_name)}</span></td>
    <td class="dim">${safe(a.airline_iata_code)}</td>
    <td class="dim">${safe(a.construction_number)}</td>
    <td class="dim">${safe(a.delivery_date?.substring(0,10))}</td>
    <td class="dim">${safe(a.first_flight_date?.substring(0,10))}</td>
  </tr>`).join('');

  content.innerHTML = `
    <table>
      <thead><tr>
        <th>Registration</th><th>Type</th><th>Airline</th>
        <th>IATA</th><th>C/N</th><th>Delivered</th><th>First Flight</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
};
"""

@mcp.resource(
    VIEW_AIRPLANES,
    app=AppConfig(csp=ResourceCSP(resource_domains=[CDN, "https://fonts.googleapis.com", "https://fonts.gstatic.com"])),
)
def airplanes_table_ui() -> str:
    """Aircraft registration lookup results."""
    return _html_shell("Aircraft Registry", "🛩", AIRPLANES_TABLE_JS)


# ─── Routes Table UI ──────────────────────────────────────────────────────────

ROUTES_TABLE_JS = """
function safe(v) { return v || '—'; }

window.__onData = function(d) {
  const items = d.routes || d.data || [];
  const badge = document.getElementById('count-badge');
  if (badge) { badge.textContent = items.length + ' routes'; badge.className = 'badge count-badge'; }

  const content = document.getElementById('content');
  content.style.display = '';
  document.getElementById('loading')?.remove();

  if (!items.length) {
    content.innerHTML = '<div class="empty-state">⚠ No routes found.</div>';
    return;
  }

  const rows = items.map(r => `<tr>
    <td>
      <span class="bold">${safe(r.departure?.iata)}</span>
      <span class="route-arrow">→</span>
      <span class="bold">${safe(r.arrival?.iata)}</span>
    </td>
    <td class="dim">${safe(r.departure?.airport)?.substring(0,24)}</td>
    <td class="dim">${safe(r.arrival?.airport)?.substring(0,24)}</td>
    <td><span class="bold cyan">${safe(r.airline?.name)}</span></td>
    <td class="dim">${safe(r.flight?.iata)}</td>
    <td class="dim">${safe(r.aircraft?.iata)}</td>
  </tr>`).join('');

  content.innerHTML = `
    <table>
      <thead><tr>
        <th>Route</th><th>Departure Airport</th><th>Arrival Airport</th>
        <th>Airline</th><th>Flight No.</th><th>Aircraft</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
};
"""

@mcp.resource(
    VIEW_ROUTES,
    app=AppConfig(csp=ResourceCSP(resource_domains=[CDN, "https://fonts.googleapis.com", "https://fonts.gstatic.com"])),
)
def routes_table_ui() -> str:
    """Airline route lookup results."""
    return _html_shell("Route Explorer", "🗺", ROUTES_TABLE_JS)


# ─── Health check ─────────────────────────────────────────────────────────────

@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "server": "AviationStack MCP", "version": "1.0.0"})


# ─── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))