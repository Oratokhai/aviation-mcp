"""
AviationStack MCP Client
========================
A FastMCP async client for interacting with the AviationStack MCP server.

Usage:
    python aviation_client.py                          # Interactive menu
    python aviation_client.py flights --dep LOS        # CLI direct call
    python aviation_client.py airports --search Lagos  # CLI direct call

Supports both local (in-process) and remote (HTTP) server connections.
"""

import asyncio
import json
import os
import sys
import argparse
from typing import Any

from fastmcp import Client, FastMCP


# ─── Connection helpers ────────────────────────────────────────────────────────

def get_client(mode: str = "http") -> Client:
    """
    Return a configured Client.

    mode="http"    → connects to HTTP server (Railway or local)
    mode="local"   → imports and connects in-process (no network, good for tests)
    """
    if mode == "local":
        # Import the server module and connect in-process
        sys.path.insert(0, os.path.dirname(__file__))
        from aviation_server import mcp as server
        return Client(server)
    else:
        url = os.environ.get("MCP_SERVER_URL", "http://localhost:8000/mcp")
        return Client(url)


# ─── Pretty printer ───────────────────────────────────────────────────────────

def pprint(label: str, data: Any):
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")
    if isinstance(data, (dict, list)):
        print(json.dumps(data, indent=2, default=str))
    else:
        print(data)


def print_flights(flights: list[dict]):
    if not flights:
        print("  (no flights returned)")
        return
    header = f"{'FLIGHT':<10} {'FROM':<6} {'TO':<6} {'STATUS':<12} {'SCHED DEP':<8} {'DELAY'}"
    print(f"\n  {header}")
    print(f"  {'─' * len(header)}")
    for f in flights:
        dep  = f.get("departure", {})
        arr  = f.get("arrival", {})
        fl   = f.get("flight", {})
        st   = f.get("flight_status", "?")
        sched = (dep.get("scheduled") or "")[:16].replace("T", " ")
        delay = dep.get("delay")
        delay_str = f"+{delay}m" if delay else "on time"
        print(f"  {fl.get('iata','?'):<10} {dep.get('iata','?'):<6} {arr.get('iata','?'):<6} "
              f"{st:<12} {sched:<17} {delay_str}")


def print_airports(airports: list[dict]):
    if not airports:
        print("  (no airports returned)")
        return
    for a in airports:
        print(f"  [{a.get('iata_code','?')}] {a.get('airport_name','?')} "
              f"— {a.get('city_iata_code','?')}, {a.get('country_name','?')}")


def print_airlines(airlines: list[dict]):
    if not airlines:
        print("  (no airlines returned)")
        return
    for a in airlines:
        print(f"  [{a.get('iata_code','?')}] {a.get('airline_name','?')} "
              f"({a.get('country_name','?')}) — status: {a.get('status','?')}")


def print_routes(routes: list[dict]):
    if not routes:
        print("  (no routes returned)")
        return
    for r in routes:
        dep = r.get("departure", {})
        arr = r.get("arrival", {})
        al  = r.get("airline", {})
        fl  = r.get("flight", {})
        print(f"  {dep.get('iata','?')} → {arr.get('iata','?')}  "
              f"{al.get('name','?')} [{fl.get('iata','?')}]")


def print_airplanes(planes: list[dict]):
    if not planes:
        print("  (no aircraft returned)")
        return
    for p in planes:
        print(f"  [{p.get('registration_number','?')}] {p.get('iata_type','?')} "
              f"— {p.get('airline_name','?')}")


# ─── Core client functions ────────────────────────────────────────────────────

async def list_tools(client: Client):
    """List all tools available on the server."""
    tools = await client.list_tools()
    print(f"\n  {len(tools)} tools available on server:\n")
    for t in tools:
        print(f"  ✦ {t.name:<30} {t.description[:60] if t.description else ''}")


async def call_get_flights(
    client: Client,
    dep_iata: str | None = None,
    arr_iata: str | None = None,
    flight_iata: str | None = None,
    airline_iata: str | None = None,
    flight_status: str | None = None,
    flight_date: str | None = None,
    limit: int = 10,
):
    result = await client.call_tool("get_flights", {
        "dep_iata": dep_iata,
        "arr_iata": arr_iata,
        "flight_iata": flight_iata,
        "airline_iata": airline_iata,
        "flight_status": flight_status,
        "flight_date": flight_date,
        "limit": limit,
    })
    sc = result.data if hasattr(result, "data") else {}
    if isinstance(sc, dict):
        flights = sc.get("flights", [])
    else:
        flights = []
    pprint("get_flights", f"Returned {len(flights)} flight(s)")
    print_flights(flights)
    return flights


async def call_get_airports(
    client: Client,
    search: str | None = None,
    iata_code: str | None = None,
    country_iso2: str | None = None,
    limit: int = 10,
):
    result = await client.call_tool("get_airports", {
        "search": search,
        "iata_code": iata_code,
        "country_iso2": country_iso2,
        "limit": limit,
    })
    sc = result.data if hasattr(result, "data") else {}
    airports = sc.get("airports", []) if isinstance(sc, dict) else []
    pprint("get_airports", f"Returned {len(airports)} airport(s)")
    print_airports(airports)
    return airports


async def call_get_airlines(
    client: Client,
    search: str | None = None,
    iata_code: str | None = None,
    country_iso2: str | None = None,
    limit: int = 10,
):
    result = await client.call_tool("get_airlines", {
        "search": search,
        "iata_code": iata_code,
        "country_iso2": country_iso2,
        "limit": limit,
    })
    sc = result.data if hasattr(result, "data") else {}
    airlines = sc.get("airlines", []) if isinstance(sc, dict) else []
    pprint("get_airlines", f"Returned {len(airlines)} airline(s)")
    print_airlines(airlines)
    return airlines


async def call_get_routes(
    client: Client,
    dep_iata: str | None = None,
    arr_iata: str | None = None,
    airline_iata: str | None = None,
    limit: int = 10,
):
    result = await client.call_tool("get_routes", {
        "dep_iata": dep_iata,
        "arr_iata": arr_iata,
        "airline_iata": airline_iata,
        "limit": limit,
    })
    sc = result.data if hasattr(result, "data") else {}
    routes = sc.get("routes", []) if isinstance(sc, dict) else []
    pprint("get_routes", f"Returned {len(routes)} route(s)")
    print_routes(routes)
    return routes


async def call_get_airplanes(
    client: Client,
    search: str | None = None,
    registration_number: str | None = None,
    airline_iata: str | None = None,
    limit: int = 10,
):
    result = await client.call_tool("get_airplanes", {
        "search": search,
        "registration_number": registration_number,
        "airline_iata": airline_iata,
        "limit": limit,
    })
    sc = result.data if hasattr(result, "data") else {}
    planes = sc.get("airplanes", []) if isinstance(sc, dict) else []
    pprint("get_airplanes", f"Returned {len(planes)} aircraft")
    print_airplanes(planes)
    return planes


# ─── Interactive menu ─────────────────────────────────────────────────────────

BANNER = """
╔══════════════════════════════════════════════════════╗
║       AviationStack MCP — Client Console             ║
║       360 Automation // David Oratokhai              ║
╚══════════════════════════════════════════════════════╝
"""

MENU = """
  [1] List all server tools
  [2] Get flights (real-time)
  [3] Get airports
  [4] Get airlines
  [5] Get routes
  [6] Get airplanes
  [q] Quit

"""

async def interactive(client: Client):
    print(BANNER)
    while True:
        print(MENU)
        choice = input("  > ").strip().lower()

        if choice == "q":
            print("\n  Disconnecting. Goodbye.\n")
            break

        elif choice == "1":
            await list_tools(client)

        elif choice == "2":
            dep = input("  Departure IATA (e.g. LOS, leave blank to skip): ").strip() or None
            arr = input("  Arrival IATA (leave blank to skip): ").strip() or None
            status = input("  Status (active/scheduled/landed/cancelled, blank=all): ").strip() or None
            limit = int(input("  Limit [10]: ").strip() or "10")
            await call_get_flights(client, dep_iata=dep, arr_iata=arr,
                                   flight_status=status, limit=limit)

        elif choice == "3":
            search = input("  Search (airport name/city, blank=skip): ").strip() or None
            iata = input("  IATA code (blank=skip): ").strip() or None
            country = input("  Country ISO2 e.g. NG (blank=skip): ").strip() or None
            await call_get_airports(client, search=search, iata_code=iata,
                                    country_iso2=country)

        elif choice == "4":
            search = input("  Search (airline name, blank=skip): ").strip() or None
            iata = input("  IATA code e.g. LH (blank=skip): ").strip() or None
            country = input("  Country ISO2 (blank=skip): ").strip() or None
            await call_get_airlines(client, search=search, iata_code=iata,
                                    country_iso2=country)

        elif choice == "5":
            dep = input("  Departure IATA: ").strip() or None
            arr = input("  Arrival IATA: ").strip() or None
            airline = input("  Airline IATA (blank=skip): ").strip() or None
            await call_get_routes(client, dep_iata=dep, arr_iata=arr,
                                  airline_iata=airline)

        elif choice == "6":
            search = input("  Search (blank=skip): ").strip() or None
            reg = input("  Registration number (blank=skip): ").strip() or None
            airline = input("  Airline IATA (blank=skip): ").strip() or None
            await call_get_airplanes(client, search=search,
                                     registration_number=reg, airline_iata=airline)

        else:
            print("  Unknown option. Try again.")


# ─── CLI parser ───────────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        prog="aviation_client",
        description="AviationStack MCP Client — 360 Automation",
    )
    parser.add_argument(
        "--mode", choices=["http", "local"], default="http",
        help="Connection mode: 'http' (default) or 'local' (in-process)"
    )
    sub = parser.add_subparsers(dest="command")

    # flights
    p_flights = sub.add_parser("flights", help="Get real-time flights")
    p_flights.add_argument("--dep", help="Departure IATA code")
    p_flights.add_argument("--arr", help="Arrival IATA code")
    p_flights.add_argument("--flight", help="Flight IATA number")
    p_flights.add_argument("--airline", help="Airline IATA code")
    p_flights.add_argument("--status", help="Flight status filter")
    p_flights.add_argument("--date", help="Historical date YYYY-MM-DD")
    p_flights.add_argument("--limit", type=int, default=10)

    # airports
    p_airports = sub.add_parser("airports", help="Airport lookup")
    p_airports.add_argument("--search", help="Free-text search")
    p_airports.add_argument("--iata", help="IATA code")
    p_airports.add_argument("--country", help="Country ISO2")
    p_airports.add_argument("--limit", type=int, default=10)

    # airlines
    p_airlines = sub.add_parser("airlines", help="Airline lookup")
    p_airlines.add_argument("--search", help="Free-text search")
    p_airlines.add_argument("--iata", help="IATA code")
    p_airlines.add_argument("--country", help="Country ISO2")
    p_airlines.add_argument("--limit", type=int, default=10)

    # routes
    p_routes = sub.add_parser("routes", help="Route lookup")
    p_routes.add_argument("--dep", help="Departure IATA code")
    p_routes.add_argument("--arr", help="Arrival IATA code")
    p_routes.add_argument("--airline", help="Airline IATA code")
    p_routes.add_argument("--limit", type=int, default=10)

    # airplanes
    p_planes = sub.add_parser("airplanes", help="Aircraft lookup")
    p_planes.add_argument("--search", help="Free-text search")
    p_planes.add_argument("--reg", help="Registration number")
    p_planes.add_argument("--airline", help="Airline IATA code")
    p_planes.add_argument("--limit", type=int, default=10)

    # tools
    sub.add_parser("tools", help="List all available tools")

    return parser


async def run_cli(args):
    client = get_client(args.mode)
    async with client:
        cmd = args.command
        if cmd == "tools" or cmd is None:
            if cmd is None:
                await interactive(client)
            else:
                await list_tools(client)
        elif cmd == "flights":
            await call_get_flights(
                client, dep_iata=args.dep, arr_iata=args.arr,
                flight_iata=args.flight, airline_iata=args.airline,
                flight_status=args.status, flight_date=args.date,
                limit=args.limit,
            )
        elif cmd == "airports":
            await call_get_airports(
                client, search=args.search, iata_code=args.iata,
                country_iso2=args.country, limit=args.limit,
            )
        elif cmd == "airlines":
            await call_get_airlines(
                client, search=args.search, iata_code=args.iata,
                country_iso2=args.country, limit=args.limit,
            )
        elif cmd == "routes":
            await call_get_routes(
                client, dep_iata=args.dep, arr_iata=args.arr,
                airline_iata=args.airline, limit=args.limit,
            )
        elif cmd == "airplanes":
            await call_get_airplanes(
                client, search=args.search, registration_number=args.reg,
                airline_iata=args.airline, limit=args.limit,
            )


def main():
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(run_cli(args))


if __name__ == "__main__":
    main()