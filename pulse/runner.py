"""Process ownership for an explicitly requested runner without a terminal."""
from __future__ import annotations

import contextlib
import os
import re
import select
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path

from pulse import actions, config, go, state


def _current(root):
    report = go.last_run(root) or {}
    run = report.get("run", {})
    try:
        pid = int((config.pulse_dir(root) / "go.pid").read_text())
    except (OSError, ValueError):
        return None
    if not run.get("running") or not run.get("id") or pid <= 0 or run.get("pid") != pid:
        return None
    with actions._directory(root) as (folder, _):
        log = str(folder / f"runner-{run['id']}.log") if run.get("managed") else ""
    return {"status": "running", "run_id": run["id"], "pid": pid,
            "report": str(config.pulse_dir(root) / "go" / "report.json"), "log": log,
            "why": (report.get("activity") or {}).get("title", "runner is active"), "goal": report.get("goal")}


def start(root, *, timeout=5.0, spawn=subprocess.Popen, cap=None, agent=None):
    """Transfer the existing exclusive lock; acknowledge only the child's saved report."""
    root, lock, process, read_fd, write_fd = Path(root).resolve(), None, None, None, None
    run_id, deadline = uuid.uuid4().hex, time.monotonic() + timeout
    receipt = {"status": "error", "run_id": run_id, "pid": None,
               "report": str(config.pulse_dir(root) / "go" / "report.json"), "log": "", "why": ""}
    try:
        while lock is None:
            try:
                lock, _ = go._lock(config.pulse_dir(root))
            except state.StateError:
                current = _current(root)
                if current:
                    return current
                if time.monotonic() >= deadline:
                    raise state.StateError("existing runner has not confirmed its startup")
                time.sleep(.02)
        with actions._directory(root) as (folder, directory):
            name = f"runner-{run_id}.log"
            receipt["log"] = str(folder / name)
            log_fd = actions._file(directory, name)
            try:
                read_fd, write_fd = os.pipe()
                argv = [sys.executable, "-m", "pulse.runner", str(root), str(lock.fileno()), str(write_fd), run_id]
                if cap is not None or agent is not None:
                    argv += [str(cap) if cap is not None else "", agent or ""]
                process = spawn(argv, cwd=Path(__file__).resolve().parents[1], stdin=subprocess.DEVNULL,
                                stdout=log_fd, stderr=subprocess.STDOUT, start_new_session=True,
                                pass_fds=(lock.fileno(), write_fd))
            finally:
                os.close(log_fd)
        os.close(write_fd)
        write_fd = None
        receipt["pid"] = process.pid
        readable, _, _ = select.select([read_fd], [], [], max(0, deadline - time.monotonic()))
        acknowledged = os.read(read_fd, 128).decode("ascii") if readable else ""
        current = _current(root)
        if acknowledged == run_id and current and current["pid"] == process.pid and current["run_id"] == run_id:
            return {**current, "status": "started"}
        report = go.last_run(root) or {}
        run = report.get("run", {})
        if acknowledged == run_id and run.get("id") == run_id and run.get("pid") == process.pid and run.get("ended"):
            why = report.get("halt") or (f"runner stopped ({run['stopped']})" if run.get("stopped") else
                                         "runner completed")
            return {**receipt, "status": "finished", "why": why, "goal": report.get("goal")}
        raise state.StateError("runner exited before startup confirmation" if process.poll() is not None else
                               "runner did not confirm startup; inspect its log")
    except (state.StateError, OSError, ValueError) as error:
        receipt["why"] = str(error) if isinstance(error, state.StateError) else \
            "runner could not start (" + type(error).__name__ + "); inspect its log"
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        # This launcher still owns the inherited lease. Never clear another run's PID.
        if lock is not None:
            pid_path = config.pulse_dir(root) / "go.pid"
            with contextlib.suppress(OSError, ValueError):
                if int(pid_path.read_text()) in {os.getpid(), process.pid if process else None}:
                    pid_path.unlink()
        return receipt
    finally:
        for fd in (read_fd, write_fd):
            if fd is not None:
                os.close(fd)
        if lock is not None:
            lock.close()


def _stop_name(run_id):
    if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,80}", run_id):
        raise state.StateError("invalid runner identifier")
    return f"runner-stop-{run_id}"


def stop(root, run_id):
    """Accept a request for this run only. CLI checks the requesting person's source."""
    name = _stop_name(run_id)
    report = go.last_run(root) or {}
    run = report.get("run", {})
    if run.get("id") != run_id:
        return {"status": "conflict", "run_id": run_id, "why": "runner changed; read its current state"}
    if not run.get("running"):
        return {"status": "stopped", "run_id": run_id, "why": "runner has ended"}
    with actions._directory(root) as (_, directory):
        fd = actions._file(directory, name)
        try:
            os.fsync(fd)
            os.fsync(directory)
        finally:
            os.close(fd)
    return {"status": "stopping", "run_id": run_id, "why": "stop requested; work will be preserved"}


def stopping(root, run_id):
    with actions._directory(root) as (_, directory):
        try:
            fd = actions._file(directory, _stop_name(run_id), create=False)
        except FileNotFoundError:
            return False
        os.close(fd)
        return True


def main():
    root, lock_fd, ready_fd, run_id = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    lock = os.fdopen(lock_fd, "r+", encoding="utf-8")
    try:
        wanted = os.stat(config.pulse_dir(root) / "go" / "lock", follow_symlinks=False)
        actual = os.fstat(lock_fd)
        if not stat.S_ISREG(wanted.st_mode) or (wanted.st_dev, wanted.st_ino) != (actual.st_dev, actual.st_ino):
            raise state.StateError("runner inherited an invalid lease")

        def confirmed(report):
            current = _current(root)
            if not current or current["run_id"] != run_id or current["pid"] != os.getpid():
                raise state.StateError("runner could not persist its startup report")
            common = config.pulse_dir(root)
            for path in (Path(report["report"]), common / "go.pid", common / "go", common):
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            os.write(ready_fd, run_id.encode("ascii"))

        options = {"cap": int(sys.argv[5]) if sys.argv[5] else None, "agent": sys.argv[6] or None} \
            if len(sys.argv) > 5 else {}
        go.run(root, managed=run_id, lease=(lock, go._noted(lock)), started=confirmed, **options)
    finally:
        os.close(ready_fd)
        if not lock.closed:
            lock.close()


if __name__ == "__main__":
    main()
