from __future__ import annotations

import json
import socket
import threading
import webbrowser
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Tuple
from urllib.parse import urlparse

from engine.core.world_chunk import WorldChunk
from engine.core.world_grid import ChunkCoord, WorldGrid
from engine.missions.mission import Mission, build_spindle_missions
from engine.scenes.world_slice import _make_world_chunks, run_world_slice
from engine.world.district_state import pressure_to_district_state
from engine.world.live_run_state import load_live_run_state
from engine.world.run_report import load_run_report
from engine.world.save_manager import load_chunk_state_into


@dataclass(slots=True)
class SpindleSnapshot:
    loaded_chunk_count: int
    world_pressure_total: float
    state_counts: Dict[str, int]
    chunks: List[dict]
    missions: List[dict]
    run_state: str
    last_run_report: dict | None
    world_delta: dict | None
    live_run_state: dict | None


HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SPINDLE // Pressure-Control Chamber</title>
<style>
  :root {
    --bg: #090c10;
    --panel: #11161c;
    --panel-2: #171d24;
    --line: #2b3540;
    --text: #e8edf2;
    --muted: #9ca8b4;
    --accent: #8fd3ff;
    --accent-2: #ffd66b;
    --clear: #2f463a;
    --warm: #8f7040;
    --frayed: #a35a39;
    --hunting: #983838;
    --seized: #5d1a2a;
    --source: #8fd3ff;
    --target: #ffd66b;
    --ok: #79d37a;
    --bad: #ff8c8c;
    --busy: #f0c46d;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: radial-gradient(circle at top, #10161d, var(--bg) 55%);
    color: var(--text);
    font-family: Inter, system-ui, sans-serif;
  }
  .wrap { max-width: 1360px; margin: 0 auto; padding: 24px; }
  .title-row {
    display: flex; align-items: center; justify-content: space-between;
    gap: 16px; margin-bottom: 20px;
  }
  .title { font-size: 30px; font-weight: 800; letter-spacing: 0.06em; }
  .status-pill {
    border-radius: 999px; padding: 10px 14px; font-size: 13px; font-weight: 800;
    letter-spacing: 0.08em; border: 1px solid var(--line);
    background: #161d25; color: var(--muted);
  }
  .status-pill.idle { color: var(--ok); border-color: rgba(121,211,122,0.35); }
  .status-pill.running { color: var(--busy); border-color: rgba(240,196,109,0.35); }

  .layout { display: grid; grid-template-columns: 1.2fr 0.95fr; gap: 20px; }
  .panel {
    background: linear-gradient(180deg, var(--panel), var(--panel-2));
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 18px;
    box-shadow: 0 12px 50px rgba(0,0,0,0.28);
  }
  .section-title { font-size: 18px; font-weight: 700; letter-spacing: 0.08em; margin-bottom: 14px; }

  .stats {
    display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 10px;
    margin-bottom: 18px;
  }
  .stat {
    background: rgba(255,255,255,0.02);
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 12px;
  }
  .stat .label {
    color: var(--muted);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }
  .stat .value {
    margin-top: 6px;
    font-size: 20px;
    font-weight: 700;
  }

  .legend {
    display: flex; flex-wrap: wrap; gap: 8px 14px;
    margin-bottom: 16px; color: var(--muted); font-size: 13px;
  }
  .legend span { display: inline-flex; align-items: center; gap: 8px; }
  .swatch {
    width: 14px; height: 14px; border-radius: 4px;
    border: 1px solid rgba(255,255,255,0.14);
  }

  .map-grid { display: grid; grid-template-columns: repeat(5, minmax(96px, 1fr)); gap: 12px; }
  .chunk {
    min-height: 116px;
    border-radius: 16px;
    border: 2px solid var(--line);
    padding: 10px;
    position: relative;
    overflow: hidden;
  }
  .chunk.source { box-shadow: inset 0 0 0 2px var(--source); }
  .chunk.target { box-shadow: inset 0 0 0 2px var(--target); }
  .chunk .coord { font-size: 12px; color: #d8e0e8; opacity: 0.95; }
  .chunk .state { margin-top: 8px; font-size: 13px; font-weight: 800; letter-spacing: 0.08em; }
  .chunk .meta { margin-top: 8px; font-size: 12px; color: #edf2f7; opacity: 0.92; line-height: 1.4; }

  .chunk.clear { background: linear-gradient(180deg, rgba(47,70,58,0.95), rgba(28,35,31,0.95)); }
  .chunk.warm { background: linear-gradient(180deg, rgba(143,112,64,0.95), rgba(58,42,22,0.95)); }
  .chunk.frayed { background: linear-gradient(180deg, rgba(163,90,57,0.95), rgba(61,31,22,0.95)); }
  .chunk.hunting { background: linear-gradient(180deg, rgba(152,56,56,0.95), rgba(54,20,20,0.95)); }
  .chunk.seized { background: linear-gradient(180deg, rgba(93,26,42,0.98), rgba(39,10,18,0.98)); }

  .mission-list { display: grid; gap: 12px; margin-bottom: 18px; }
  .mission {
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 14px;
    background: rgba(255,255,255,0.02);
    cursor: pointer;
    transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
  }
  .mission:hover { transform: translateY(-1px); border-color: #4a6178; }
  .mission.selected { border-color: var(--accent-2); background: rgba(255,214,107,0.06); }
  .mission .name { font-weight: 800; letter-spacing: 0.04em; margin-bottom: 8px; }
  .mission .sub { color: var(--muted); font-size: 13px; line-height: 1.5; }

  .selected-box, .result-box, .live-box {
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 14px;
    background: rgba(255,255,255,0.02);
    margin-bottom: 16px;
  }
  .selected-box .row, .result-box .row, .live-box .row {
    margin: 6px 0; color: var(--muted);
  }
  .selected-box .row b, .result-box .row b, .live-box .row b { color: var(--text); }

  .actions { display: flex; gap: 12px; }
  button {
    border: 0; border-radius: 14px; padding: 14px 18px;
    font-size: 15px; font-weight: 800; letter-spacing: 0.04em; cursor: pointer;
  }
  .launch { background: linear-gradient(180deg, #8fd3ff, #66b7ef); color: #081018; flex: 1; }
  .refresh { background: #202833; color: var(--text); border: 1px solid var(--line); }
  .launch:disabled { opacity: 0.5; cursor: default; }
  .ok { color: var(--ok); }
  .bad { color: var(--bad); }
  .busy { color: var(--busy); }

  .footer-note { margin-top: 16px; color: var(--muted); font-size: 13px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="title-row">
    <div class="title">SPINDLE // PRESSURE-CONTROL CHAMBER</div>
    <div id="run-state" class="status-pill idle">IDLE</div>
  </div>

  <div class="layout">
    <div class="panel">
      <div class="section-title">CITY MACRO MAP</div>
      <div class="stats">
        <div class="stat">
          <div class="label">Loaded Chunks</div>
          <div class="value" id="loaded-count">--</div>
        </div>
        <div class="stat">
          <div class="label">World Pressure Total</div>
          <div class="value" id="world-pressure">--</div>
        </div>
        <div class="stat">
          <div class="label">District Counts</div>
          <div class="value" id="state-counts" style="font-size:14px; line-height:1.4;">--</div>
        </div>
        <div class="stat">
          <div class="label">Selected Route</div>
          <div class="value" id="route-readout" style="font-size:14px; line-height:1.4;">--</div>
        </div>
      </div>

      <div class="legend">
        <span><i class="swatch" style="background: var(--clear)"></i>Clear</span>
        <span><i class="swatch" style="background: var(--warm)"></i>Warm</span>
        <span><i class="swatch" style="background: var(--frayed)"></i>Frayed</span>
        <span><i class="swatch" style="background: var(--hunting)"></i>Hunting</span>
        <span><i class="swatch" style="background: var(--seized)"></i>Seized</span>
        <span><i class="swatch" style="background: transparent; border-color: var(--source)"></i>Source</span>
        <span><i class="swatch" style="background: transparent; border-color: var(--target)"></i>Target</span>
      </div>

      <div id="map" class="map-grid"></div>
    </div>

    <div class="panel">
      <div class="section-title">DISPATCH</div>
      <div id="missions" class="mission-list"></div>

      <div class="selected-box">
        <div class="section-title" style="margin-bottom: 10px;">SELECTED RUN</div>
        <div class="row"><b>Label:</b> <span id="sel-label">--</span></div>
        <div class="row"><b>Type:</b> <span id="sel-type">--</span></div>
        <div class="row"><b>Cargo:</b> <span id="sel-cargo">--</span></div>
        <div class="row"><b>Pickup:</b> <span id="sel-source">--</span></div>
        <div class="row"><b>Delivery:</b> <span id="sel-target">--</span></div>
      </div>

      <div id="live-box" class="live-box" style="display:none;">
        <div class="section-title" style="margin-bottom: 10px;">LIVE RUN HUD</div>
        <div class="row"><b>Time:</b> <span id="live-time">--</span></div>
        <div class="row"><b>Mission Phase:</b> <span id="live-phase">--</span></div>
        <div class="row"><b>Cargo:</b> <span id="live-cargo">--</span></div>
        <div class="row"><b>Player Chunk:</b> <span id="live-chunk">--</span></div>
        <div class="row"><b>Zone Archetype:</b> <span id="live-zone-archetype">--</span></div>
        <div class="row"><b>Zone State:</b> <span id="live-zone-band">--</span></div>
        <div class="row"><b>Local Pressure:</b> <span id="live-pressure">--</span></div>
        <div class="row"><b>Strain:</b> <span id="live-strain">--</span></div>
        <div class="row"><b>Survival State:</b> <span id="live-survival">--</span></div>
        <div class="row"><b>Objective:</b> <span id="live-objective">--</span></div>
      </div>

      <div id="result-box" class="result-box" style="display:none;">
        <div class="section-title" style="margin-bottom: 10px;">LAST RUN RESULT</div>
        <div class="row"><b>Mission:</b> <span id="res-mission">--</span></div>
        <div class="row"><b>Outcome:</b> <span id="res-outcome">--</span></div>
        <div class="row"><b>Failure:</b> <span id="res-failure">--</span></div>
        <div class="row"><b>Pressure Δ:</b> <span id="res-pressure-delta">--</span></div>
        <div class="row"><b>State Δ:</b> <span id="res-state-delta">--</span></div>
      </div>

      <div class="actions">
        <button class="launch" id="launch-btn">LAUNCH RUN</button>
        <button class="refresh" id="refresh-btn">REFRESH</button>
      </div>

      <div class="footer-note">
        The Spindle is not a menu. It is a control chamber.
        Read the city, choose a line, accept the cost.
      </div>
    </div>
  </div>
</div>

<script>
let snapshot = null;
let selectedIndex = 0;

function fmtCoord(coord) {
  if (!coord) return "--";
  return `(${coord[0]}, ${coord[1]})`;
}

function setRunState(runState) {
  const el = document.getElementById("run-state");
  el.textContent = runState.toUpperCase();
  el.className = "status-pill " + (runState === "running" ? "running" : "idle");
  const btn = document.getElementById("launch-btn");
  btn.disabled = runState === "running";
  btn.textContent = runState === "running" ? "RUNNING..." : "LAUNCH RUN";
}

function renderStats() {
  document.getElementById("loaded-count").textContent = snapshot.loaded_chunk_count;
  document.getElementById("world-pressure").textContent = snapshot.world_pressure_total.toFixed(2);
  document.getElementById("state-counts").innerHTML =
    `clear=${snapshot.state_counts.clear || 0}<br>` +
    `warm=${snapshot.state_counts.warm || 0}<br>` +
    `frayed=${snapshot.state_counts.frayed || 0}<br>` +
    `hunting=${snapshot.state_counts.hunting || 0}<br>` +
    `seized=${snapshot.state_counts.seized || 0}`;

  const mission = snapshot.missions[selectedIndex];
  document.getElementById("route-readout").innerHTML =
    `${fmtCoord(mission.source)} &rarr; ${fmtCoord(mission.target)}<br>${mission.cargo_type}`;
}

function renderMap() {
  const map = document.getElementById("map");
  map.innerHTML = "";

  const mission = snapshot.missions[selectedIndex];
  const sorted = [...snapshot.chunks].sort((a, b) => {
    if (a.coord[1] !== b.coord[1]) return b.coord[1] - a.coord[1];
    return a.coord[0] - b.coord[0];
  });

  for (const chunk of sorted) {
    const div = document.createElement("div");
    div.className = `chunk ${chunk.district_state}`;

    if (chunk.coord[0] === mission.source[0] && chunk.coord[1] === mission.source[1]) {
      div.classList.add("source");
    }
    if (chunk.coord[0] === mission.target[0] && chunk.coord[1] === mission.target[1]) {
      div.classList.add("target");
    }

    div.innerHTML = `
      <div class="coord">${fmtCoord(chunk.coord)}</div>
      <div class="state">${chunk.district_state.toUpperCase()}</div>
      <div class="meta">
        archetype=${chunk.archetype}<br>
        pressure=${chunk.pressure.toFixed(2)}
      </div>
    `;
    map.appendChild(div);
  }
}

function renderMissions() {
  const wrap = document.getElementById("missions");
  wrap.innerHTML = "";

  snapshot.missions.forEach((mission, idx) => {
    const card = document.createElement("div");
    card.className = "mission" + (idx === selectedIndex ? " selected" : "");
    card.onclick = () => {
      selectedIndex = idx;
      renderAll();
    };
    card.innerHTML = `
      <div class="name">${mission.label.toUpperCase()}</div>
      <div class="sub">
        cargo=${mission.cargo_type}<br>
        source=${fmtCoord(mission.source)}<br>
        target=${fmtCoord(mission.target)}
      </div>
    `;
    wrap.appendChild(card);
  });
}

function renderSelection() {
  const mission = snapshot.missions[selectedIndex];
  document.getElementById("sel-label").textContent = mission.label;
  document.getElementById("sel-type").textContent = mission.mission_type;
  document.getElementById("sel-cargo").textContent = mission.cargo_type;
  document.getElementById("sel-source").textContent = fmtCoord(mission.source);
  document.getElementById("sel-target").textContent = fmtCoord(mission.target);
}

function renderLiveRun() {
  const box = document.getElementById("live-box");
  const live = snapshot.live_run_state;

  if (!live || snapshot.run_state !== "running") {
    box.style.display = "none";
    return;
  }

  box.style.display = "block";
  document.getElementById("live-time").textContent = `${live.time_s}s`;
  document.getElementById("live-phase").textContent = live.mission?.phase || "--";
  document.getElementById("live-cargo").textContent = live.mission?.cargo || "--";
  document.getElementById("live-chunk").textContent = fmtCoord(live.player?.chunk);
  document.getElementById("live-zone-archetype").textContent = live.player?.zone_archetype || "--";
  document.getElementById("live-zone-band").textContent = live.player?.zone_band || "--";
  document.getElementById("live-pressure").textContent = typeof live.player?.local_pressure === "number"
    ? live.player.local_pressure.toFixed(2)
    : "--";
  document.getElementById("live-strain").textContent = typeof live.player?.strain === "number"
    ? live.player.strain.toFixed(1)
    : "--";
  document.getElementById("live-survival").textContent = live.player?.survival_state || "--";
  document.getElementById("live-objective").textContent = live.objective_text || "--";
}

function renderLastRun() {
  const box = document.getElementById("result-box");
  const report = snapshot.last_run_report;
  if (!report) {
    box.style.display = "none";
    return;
  }
  box.style.display = "block";

  const mission = report.mission || {};
  const delta = snapshot.world_delta || {};

  document.getElementById("res-mission").textContent = mission.label || "--";
  const outcomeEl = document.getElementById("res-outcome");
  const completed = !!mission.completed;
  const failed = !!mission.failed;
  if (completed) {
    outcomeEl.textContent = "COMPLETED";
    outcomeEl.className = "ok";
  } else if (failed) {
    outcomeEl.textContent = "FAILED";
    outcomeEl.className = "bad";
  } else {
    outcomeEl.textContent = mission.phase || "--";
    outcomeEl.className = "";
  }

  document.getElementById("res-failure").textContent = mission.failure_reason || "none";

  const pressureDelta = typeof delta.world_pressure_delta === "number"
    ? delta.world_pressure_delta.toFixed(2)
    : "--";
  document.getElementById("res-pressure-delta").textContent = pressureDelta;

  const stateDelta = delta.state_count_delta || {};
  const pieces = [];
  for (const key of ["clear", "warm", "frayed", "hunting", "seized"]) {
    if (stateDelta[key]) {
      pieces.push(`${key}=${stateDelta[key] > 0 ? "+" : ""}${stateDelta[key]}`);
    }
  }
  document.getElementById("res-state-delta").textContent = pieces.length ? pieces.join(", ") : "no change";
}

function renderAll() {
  setRunState(snapshot.run_state);
  renderStats();
  renderMap();
  renderMissions();
  renderSelection();
  renderLiveRun();
  renderLastRun();
}

async function loadState() {
  const res = await fetch("/api/state");
  snapshot = await res.json();
  if (selectedIndex >= snapshot.missions.length) selectedIndex = 0;
  renderAll();
}

async function launchRun() {
  const res = await fetch("/api/launch", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ mission_index: selectedIndex })
  });
  const data = await res.json();
  if (data.ok) {
    await loadState();
  }
}

document.getElementById("refresh-btn").onclick = loadState;
document.getElementById("launch-btn").onclick = launchRun;

setInterval(loadState, 1000);
loadState();
</script>
</body>
</html>
"""


def _state_counts(chunks: Dict[ChunkCoord, WorldChunk]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for chunk in chunks.values():
        counts[chunk.district_state] = counts.get(chunk.district_state, 0) + 1
    return counts


def _world_pressure_total(chunks: Dict[ChunkCoord, WorldChunk]) -> float:
    return sum(chunk.state.pressure for chunk in chunks.values())


def _build_world(
    *,
    save_path: str,
    chunk_width: float,
    chunk_height: float,
) -> tuple[WorldGrid, Dict[ChunkCoord, WorldChunk], int, List[Mission]]:
    grid = WorldGrid(chunk_width=chunk_width, chunk_height=chunk_height)
    chunks = _make_world_chunks(grid)
    for chunk in chunks.values():
        chunk.district_state = pressure_to_district_state(chunk.state.pressure).value

    loaded_chunk_count = load_chunk_state_into(chunks, save_path)
    for chunk in chunks.values():
        chunk.district_state = pressure_to_district_state(chunk.state.pressure).value

    missions = build_spindle_missions(chunks)
    return grid, chunks, loaded_chunk_count, missions


def _build_snapshot(
    chunks: Dict[ChunkCoord, WorldChunk],
    loaded_chunk_count: int,
    missions: List[Mission],
    *,
    run_state: str,
    last_run_report: dict | None,
    world_delta: dict | None,
    live_run_state: dict | None,
) -> SpindleSnapshot:
    chunk_rows = []
    for coord in sorted(chunks.keys()):
        chunk = chunks[coord]
        chunk_rows.append(
            {
                "coord": [coord[0], coord[1]],
                "district_state": chunk.district_state,
                "pressure": float(chunk.state.pressure),
                "archetype": chunk.archetype,
            }
        )

    mission_rows = []
    for mission in missions:
        mission_rows.append(
            {
                "label": mission.label,
                "mission_type": mission.mission_type.value,
                "cargo_type": mission.cargo_type.value,
                "source": [mission.source[0], mission.source[1]],
                "target": [mission.target[0], mission.target[1]],
            }
        )

    return SpindleSnapshot(
        loaded_chunk_count=loaded_chunk_count,
        world_pressure_total=_world_pressure_total(chunks),
        state_counts=_state_counts(chunks),
        chunks=chunk_rows,
        missions=mission_rows,
        run_state=run_state,
        last_run_report=last_run_report,
        world_delta=world_delta,
        live_run_state=live_run_state,
    )


def _find_free_port(host: str, start: int = 8765, attempts: int = 20) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError("Could not find a free port for Spindle.")


def run_spindle_web(
    *,
    save_path: str = "runtime/world_state.json",
    report_path: str = "runtime/last_run_report.json",
    live_state_path: str = "runtime/live_run_state.json",
    chunk_width: float = 256.0,
    chunk_height: float = 256.0,
    host: str = "127.0.0.1",
    port: int | None = None,
    open_browser: bool = True,
    run_duration: float = 20.0,
    run_fps: float = 60.0,
    run_use_graphics: bool = True,
    run_debug_level: str = "full",
) -> None:
    lock = threading.Lock()

    _, chunks, loaded_chunk_count, missions = _build_world(
        save_path=save_path,
        chunk_width=chunk_width,
        chunk_height=chunk_height,
    )

    state = {
        "run_state": "idle",
        "last_run_report": load_run_report(report_path),
        "world_delta": None,
    }

    def rebuild_world() -> tuple[Dict[ChunkCoord, WorldChunk], int, List[Mission]]:
        _, new_chunks, new_loaded_chunk_count, new_missions = _build_world(
            save_path=save_path,
            chunk_width=chunk_width,
            chunk_height=chunk_height,
        )
        return new_chunks, new_loaded_chunk_count, new_missions

    def current_snapshot() -> SpindleSnapshot:
        live = load_live_run_state(live_state_path)
        return _build_snapshot(
            chunks,
            loaded_chunk_count,
            missions,
            run_state=state["run_state"],
            last_run_report=state["last_run_report"],
            world_delta=state["world_delta"],
            live_run_state=live,
        )

    def run_selected_mission(mission: Mission, before_pressure: float, before_counts: Dict[str, int]) -> None:
        try:
            run_world_slice(
                duration=run_duration,
                fps=run_fps,
                use_graphics=run_use_graphics,
                debug_level=run_debug_level,
                save_path=save_path,
                report_path=report_path,
                live_state_path=live_state_path,
                mission=mission,
            )
        finally:
            with lock:
                nonlocal chunks, loaded_chunk_count, missions
                chunks, loaded_chunk_count, missions = rebuild_world()
                after_pressure = _world_pressure_total(chunks)
                after_counts = _state_counts(chunks)

                delta: Dict[str, int] = {}
                for key in {"clear", "warm", "frayed", "hunting", "seized"}:
                    delta[key] = after_counts.get(key, 0) - before_counts.get(key, 0)

                state["run_state"] = "idle"
                state["last_run_report"] = load_run_report(report_path)
                state["world_delta"] = {
                    "world_pressure_delta": after_pressure - before_pressure,
                    "state_count_delta": delta,
                }

    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:
            return

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/":
                self._send_html(HTML_PAGE)
                return

            if path == "/api/state":
                with lock:
                    self._send_json(asdict(current_snapshot()))
                return

            self._send_json({"ok": False, "error": "not_found"}, status=404)

        def do_POST(self) -> None:
            path = urlparse(self.path).path

            if path == "/api/launch":
                with lock:
                    if state["run_state"] == "running":
                        self._send_json({"ok": False, "error": "run_already_active"}, status=409)
                        return

                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                    except ValueError:
                        length = 0
                    raw = self.rfile.read(length) if length > 0 else b"{}"
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        payload = {}

                    try:
                        mission_index = int(payload.get("mission_index", 0))
                    except Exception:
                        mission_index = 0

                    if not (0 <= mission_index < len(missions)):
                        self._send_json({"ok": False, "error": "bad_mission_index"}, status=400)
                        return

                    mission = missions[mission_index]
                    before_pressure = _world_pressure_total(chunks)
                    before_counts = _state_counts(chunks)

                    state["run_state"] = "running"
                    state["world_delta"] = None

                    thread = threading.Thread(
                        target=run_selected_mission,
                        args=(mission, before_pressure, before_counts),
                        daemon=True,
                    )
                    thread.start()

                    self._send_json({"ok": True})
                    return

            self._send_json({"ok": False, "error": "not_found"}, status=404)

    actual_port = port if port is not None else _find_free_port(host)
    server = ThreadingHTTPServer((host, actual_port), Handler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://{host}:{actual_port}/"
    print(f"SPINDLE WEB: {url}")
    print("Leave this process running. Press Ctrl+C to stop the campaign chamber.")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        thread.join()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1.0)


if __name__ == "__main__":
    run_spindle_web()
