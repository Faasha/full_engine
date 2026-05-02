import ollama
import subprocess
import json
import os
from datetime import datetime

print("🚀 full_engine AI Co-Pilot v2 — now understands your full vision\nType 'exit' to quit.\n")

def run_launch_script(script_name="launch_campaign.py", args=""):
    try:
        cmd = ["python", script_name] + (args.split() if args else [])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=os.getcwd())
        return f"Exit code: {result.returncode}\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}"
    except Exception as e:
        return f"Error: {e}"

def read_json_file(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        return json.dumps(data, indent=2)[:2500]
    except Exception as e:
        return f"Error reading {filename}: {e}"

def analyze_latest_report():
    reports = [f for f in os.listdir("runtime") if f.startswith("probe_report_") or f == "last_run_report.json"]
    if not reports:
        return "No reports found."
    latest = max(reports, key=lambda x: os.path.getmtime(os.path.join("runtime", x)))
    return read_json_file(os.path.join("runtime", latest))

def list_engine_structure():
    structure = []
    for root, dirs, files in os.walk("."):
        if "__pycache__" in root or "final_build" in root:
            continue
        level = root.count(os.sep)
        structure.append("  " * level + os.path.basename(root) + "/")
        for f in files:
            structure.append("  " * (level + 1) + f)
    return "\n".join(structure[:80])

def safe_edit_file(filename, instruction):
    return f"Would edit {filename} with instruction: {instruction}\n(For safety, describe the exact change you want and I'll generate the full patch)"

tools = {
    "run_launch": run_launch_script,
    "read_json": read_json_file,
    "analyze_report": analyze_latest_report,
    "list_structure": list_engine_structure,
    "safe_edit": safe_edit_file,
}

system_prompt = f"""You are Liam's truth-seeking, maximally helpful AI co-pilot for **full_engine** — a high-performance ECS-based multi-agent simulation engine running 100% in Termux on Android.

PROJECT OVERVIEW (you fully understand this):
- Core: Custom ECS (Entity Component System) with native C acceleration (libfield_diffuse.so, libmovement_native.so) for speed.
- World: Flat grid + chunked world, occupancy map, field diffusion, agent movement.
- Agents: Wander system, collision, player disturbance, dissolve, activation.
- Probes & Testing: Multiple runtime probes (flat_motion, hybrid, spindle, stress_null, etc.) + JSON reports.
- Missions: Procedural mission system.
- Runtime: Live state saving, launch_campaign.py + web version, world_state.json, probe reports.
- Goal: Build the ultimate local, unlimited, high-performance simulation that can run massive agent worlds on a phone.

You have the complete folder structure memorized.

Use tools via this exact format:
Thought: [reason step by step]
Action: tool_name with arg
Observation: [result]

Available tools:
- run_launch(script_name, args)
- read_json(filename)
- analyze_report()
- list_structure()
- safe_edit(filename, instruction)

Always end with: Final Answer: [your response or summary]

Be proactive, practical, and focused on making the engine faster, smarter, or more powerful. Suggest next features, debug issues, generate new systems, or improve existing code.

Current time: {datetime.now().strftime("%Y-%m-%d %H:%M")}"""

conversation = []

while True:
    user_input = input("You: ")
    if user_input.lower() in ["exit", "quit"]:
        break
    conversation.append({"role": "user", "content": user_input})
    for step in range(15):
        response = ollama.chat(
            model='qwen3.5:0.8b',
            messages=[{"role": "system", "content": system_prompt}] + conversation
        )
        reply = response['message']['content']
        print(f"Agent: {reply}\n")
        conversation.append({"role": "assistant", "content": reply})
        if "Final Answer:" in reply:
            break
        if "Action:" in reply and "with" in reply:
            try:
                action_part = reply.split("Action:")[1].split("\n")[0].strip()
                tool_name = action_part.split("with")[0].strip()
                arg_part = action_part.split("with", 1)[1].strip().strip("()\"'")
                if tool_name in tools:
                    if tool_name == "run_launch":
                        arg = arg_part.split(",", 1)
                        script = arg[0].strip() if arg else "launch_campaign.py"
                        extra_args = arg[1].strip() if len(arg) > 1 else ""
                        obs = tools[tool_name](script, extra_args)
                    elif tool_name == "read_json":
                        obs = tools[tool_name](arg_part)
                    elif tool_name == "safe_edit":
                        parts = arg_part.split(",", 1)
                        obs = tools[tool_name](parts[0].strip(), parts[1].strip() if len(parts) > 1 else "")
                    else:
                        obs = tools[tool_name]()
                    observation = f"Observation: {obs}"
                    print(observation)
                    conversation.append({"role": "user", "content": observation})
            except:
                pass
