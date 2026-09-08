"""Spike 3 - Can Baileys and WhatsApp Desktop stay linked to one account?

The voice plan assumes both can be linked companion devices on the same WhatsApp
account at the same time:

    Business WhatsApp account
      |- Baileys linked session     -> messaging agent (already live)
      \\- WhatsApp Desktop session   -> voice companion (new)

WhatsApp allows a limited number of companion devices, and Baileys is unofficial, so
this cannot be assumed - it has to be observed. The Bonanza session already logged
itself out once during development, which is exactly the failure this watches for.

The spike polls three things on an interval and records every transition:

    1. the bridge's own /health endpoint
    2. what the bridge last reported to the backend (bridgeStatus in Mongo)
    3. whether WhatsApp Desktop is running on this machine

Run it for as long as you can - an hour proves little, overnight proves a lot:

    .venv\\Scripts\\python.exe spike3_session_coexistence.py --minutes 120
    .venv\\Scripts\\python.exe spike3_session_coexistence.py --once      (single snapshot)

Leave the Baileys bridge running and WhatsApp Desktop open and logged in while it runs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

RESULTS = Path(__file__).parent / "results" / "spike3"
BRIDGE_HEALTH = os.environ.get("BRIDGE_HEALTH", "http://127.0.0.1:3005/health")
API = os.environ.get("BIZXUS_API", "http://127.0.0.1:8000/api/v1")

# Statuses that mean the session is broken rather than merely busy.
BROKEN = {"logged_out", "connection_failed", "stopped"}
HEALTHY = {"ready"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def whatsapp_desktop_running() -> bool:
    """WhatsApp Desktop ships both as a Store app and a classic exe; check both."""
    try:
        output = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=15,
        ).stdout.lower()
    except Exception:
        return False
    return "whatsapp.exe" in output or "whatsappdesktop" in output


async def read_bridge_health(client: httpx.AsyncClient) -> dict:
    try:
        response = await client.get(BRIDGE_HEALTH, timeout=8)
        body = response.json()
    except Exception as exc:
        return {"reachable": False, "error": f"{type(exc).__name__}"}

    # The bridge serves single-tenant and multi-tenant shapes; normalise both.
    if "tenants" in body:
        tenants = [
            {"tenantId": t.get("tenantId"), "label": t.get("label"), "status": t.get("status")}
            for t in body.get("tenants", [])
        ]
    else:
        tenants = [{"tenantId": body.get("tenantId"), "label": body.get("tenantId"), "status": body.get("status")}]
    return {"reachable": True, "ready": bool(body.get("ready")), "tenants": tenants}


async def read_backend_view(client: httpx.AsyncClient) -> dict:
    """What the backend believes, which is what the owner dashboard shows."""
    try:
        response = await client.get(f"{API}/health/readiness", timeout=15)
        if response.status_code != 200:
            return {"reachable": False, "error": f"HTTP {response.status_code}"}
        checks = response.json()["data"]["checks"]
        row = next((c for c in checks if c["code"] == "whatsapp_connections"), None)
        return {"reachable": True, "status": (row or {}).get("status"), "message": (row or {}).get("message", "")}
    except Exception as exc:
        return {"reachable": False, "error": f"{type(exc).__name__}"}


def summarize(sample: dict) -> str:
    bridge = sample["bridge"]
    if not bridge.get("reachable"):
        bridge_text = f"bridge unreachable ({bridge.get('error')})"
    else:
        bridge_text = ", ".join(f"{t.get('label')}={t.get('status')}" for t in bridge.get("tenants", [])) or "no tenants"
    return f"desktop={'up' if sample['whatsappDesktop'] else 'down'} | {bridge_text}"


async def take_sample(client: httpx.AsyncClient) -> dict:
    bridge, backend = await asyncio.gather(read_bridge_health(client), read_backend_view(client))
    return {
        "at": now(),
        "whatsappDesktop": whatsapp_desktop_running(),
        "bridge": bridge,
        "backend": backend,
    }


def classify(sample: dict) -> str:
    bridge = sample["bridge"]
    if not bridge.get("reachable"):
        return "bridge_down"
    statuses = {t.get("status") for t in bridge.get("tenants", [])}
    if statuses & BROKEN:
        return "session_broken"
    if statuses and statuses <= HEALTHY:
        return "healthy"
    return "connecting"


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--minutes", type=float, default=60.0, help="How long to watch.")
    parser.add_argument("--interval", type=float, default=60.0, help="Seconds between samples.")
    parser.add_argument("--once", action="store_true", help="Take a single snapshot and exit.")
    args = parser.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    log_path = RESULTS / "timeline.jsonl"

    print("=" * 74)
    print("SPIKE 3 - Baileys and WhatsApp Desktop coexistence")
    print("=" * 74)
    print(f"bridge : {BRIDGE_HEALTH}")
    print(f"backend: {API}")
    print(f"log    : {log_path}\n")

    samples: list[dict] = []
    transitions: list[dict] = []
    previous_state: str | None = None

    async with httpx.AsyncClient() as client:
        deadline = asyncio.get_event_loop().time() + (0 if args.once else args.minutes * 60)
        while True:
            sample = await take_sample(client)
            state = classify(sample)
            sample["state"] = state
            samples.append(sample)

            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(sample) + "\n")

            marker = "  " if state == previous_state else "->"
            print(f"{marker} {sample['at']}  [{state:14}] {summarize(sample)}")
            if previous_state is not None and state != previous_state:
                transitions.append({"at": sample["at"], "from": previous_state, "to": state})
            previous_state = state

            if args.once or asyncio.get_event_loop().time() >= deadline:
                break
            await asyncio.sleep(args.interval)

    write_report(samples, transitions, args)
    print(f"\nWrote {RESULTS / 'REPORT.md'}")


def write_report(samples: list[dict], transitions: list[dict], args) -> None:
    counts: dict[str, int] = {}
    for sample in samples:
        counts[sample["state"]] = counts.get(sample["state"], 0) + 1
    total = len(samples) or 1
    healthy_pct = 100.0 * counts.get("healthy", 0) / total
    desktop_up = sum(1 for s in samples if s["whatsappDesktop"])

    lines = [
        "# Spike 3 - Baileys and WhatsApp Desktop coexistence",
        "",
        "Observes whether the messaging bridge and WhatsApp Desktop can stay linked to the",
        "same account at the same time. Baileys is unofficial, so this is measured, not assumed.",
        "",
        f"- Samples: **{len(samples)}** every {args.interval:.0f}s",
        f"- Window: {samples[0]['at'] if samples else '-'} to {samples[-1]['at'] if samples else '-'}",
        f"- Healthy: **{healthy_pct:.0f}%** of samples",
        f"- WhatsApp Desktop running in {desktop_up}/{len(samples)} samples",
        "",
        "## State breakdown",
        "",
        "| State | Samples |",
        "|---|---|",
    ]
    for state, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {state} | {count} |")

    lines += ["", "## Transitions", ""]
    if transitions:
        lines += ["| When | From | To |", "|---|---|---|"]
        lines += [f"| {t['at']} | {t['from']} | {t['to']} |" for t in transitions]
        lines += ["", "Each `-> session_broken` transition is a coexistence failure worth investigating."]
    else:
        lines.append("No state changes observed during the window.")

    lines += [
        "",
        "## What this means for the plan",
        "",
        "- **Healthy throughout**: the two sessions coexist; proceed as designed.",
        "- **Occasional `connecting`**: normal reconnect churn, tolerable.",
        "- **Any `session_broken` while Desktop was up**: the two are fighting for device slots.",
        "  Mitigation is to keep messaging and voice on separate WhatsApp accounts, and to say",
        "  so plainly in the report rather than claiming coexistence works.",
        "",
        "## Verdict (fill in)",
        "",
        "```text",
        "Observation window length:                        ______",
        "Did the Baileys session survive throughout?       ______",
        "Did WhatsApp Desktop stay logged in?              ______",
        "Coexistence acceptable for the demo? (yes/no)     ______",
        "```",
        "",
        f"Raw timeline: `{(RESULTS / 'timeline.jsonl').name}`",
    ]
    (RESULTS / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    if sys.platform != "win32":
        print("WhatsApp Desktop detection only works on Windows; other checks still run.\n")
    asyncio.run(main())
