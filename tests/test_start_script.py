import runpy
import subprocess
from pathlib import Path


def test_main_does_not_restart_bot_after_keyboard_interrupt(monkeypatch):
    calls = 0

    def interrupt_bot(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise KeyboardInterrupt

    monkeypatch.setattr(subprocess, "run", interrupt_bot)
    start_script = Path(__file__).resolve().parents[1] / "start.py"

    runpy.run_path(str(start_script), run_name="__main__")

    assert calls == 1
