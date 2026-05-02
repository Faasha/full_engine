from engine.scenes.spindle_scene import run_spindle_scene
from engine.scenes.world_slice import run_world_slice

mission = run_spindle_scene(save_path="runtime/world_state.json")
if mission is not None:
    run_world_slice(
        duration=20,
        fps=60,
        use_graphics=True,
        debug_level="full",
        save_path="runtime/world_state.json",
        mission=mission,
    )
else:
    print("campaign launch cancelled")
