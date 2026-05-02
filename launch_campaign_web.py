from engine.scenes.spindle_web import run_spindle_web

if __name__ == "__main__":
    run_spindle_web(
        save_path="runtime/world_state.json",
        report_path="runtime/last_run_report.json",
        host="0.0.0.0",
        port=8765,
        open_browser=False,
        run_duration=20.0,
        run_fps=60.0,
        run_use_graphics=True,
        run_debug_level="full",
    )
