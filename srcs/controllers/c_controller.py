import subprocess
import uuid
import multiprocessing as mp
from multiprocessing import Process
from multiprocessing.queues import Queue as MPQueue
from multiprocessing.managers import SyncManager
from pathlib import Path
from queue import Full
from typing import Any, Optional, TypedDict


ISOLATE = "isolate"
CC = "/usr/bin/gcc"

WORKERS = 4
JOB_QUEUE_MAX = 200


_ctx: Optional[mp.context.BaseContext] = None
job_queue: Optional[MPQueue] = None
manager: Optional[SyncManager] = None
jobs: Optional[dict] = None
_worker_processes: list[Process] = []

def init_mp():
	global _ctx, job_queue, manager, jobs
	if jobs is not None:
		return

	_ctx = mp.get_context("fork")
	job_queue = _ctx.Queue(maxsize=JOB_QUEUE_MAX)
	manager = _ctx.Manager()
	jobs = manager.dict()

class JobResult(TypedDict, total=False):
	status: str
	box_id: int
	stdout: str
	stderr: str
	compile_error: str
	isolate_diag: str
	error: str


def box_path(box_id: int) -> Path:
	return Path(f"/var/local/lib/isolate/{box_id}/box")


def isolate_init(box_id: int) -> None:
	subprocess.run(
		[ISOLATE, f"--box-id={box_id}", "--cleanup"],
		stdout=subprocess.DEVNULL,
		stderr=subprocess.DEVNULL,
	)
	r = subprocess.run([ISOLATE, f"--box-id={box_id}", "--init"], capture_output=True, text=True)
	if r.returncode != 0:
		raise RuntimeError(r.stderr.strip() or "isolate init failed")


def isolate_cleanup(box_id: int) -> None:
	subprocess.run(
		[ISOLATE, f"--box-id={box_id}", "--cleanup"],
		stdout=subprocess.DEVNULL,
		stderr=subprocess.DEVNULL,
	)


def run_job_in_box(box_id: int, job_id: str, program: dict[str, Any]) -> None:
	try:
		isolate_init(box_id)
		p = box_path(box_id)

		(p / "main.c").write_text(program["code"], encoding="utf-8")
		if program.get("stdin") is not None:
			(p / "input.txt").write_text(program["stdin"], encoding="utf-8")

		compile_cmd = [
			ISOLATE,
			f"--box-id={box_id}",
			"--processes=64",
			"--run",
			"--env=PATH=/usr/bin:/bin",
			"--chdir=/box",
			"--",
			CC,
			"main.c",
			"-o",
			"main",
			"-B/usr/bin",
		]
		c = subprocess.run(compile_cmd, capture_output=True, text=True)
		if c.returncode != 0:
			jobs[job_id] = {**jobs[job_id], "status": "failed", "error": c.stderr.strip()}
			return

		if not (p / "main").exists():
			jobs[job_id] = {**jobs[job_id], "status": "failed", "error": "compile failed: output binary not found"}
			return

		run_cmd = [
			ISOLATE,
			f"--box-id={box_id}",
			"--time=1",
			"--mem=262144",
			"--stdout=out.txt",
			"--stderr=err.txt",
		]
		if program.get("stdin") is not None:
			run_cmd.append("--stdin=input.txt")
		run_cmd += [
			"--run",
			"--",
			"./main"
		]

		r = subprocess.run(run_cmd, capture_output=True, text=True)

		stdout = (p / "out.txt").read_text(errors="replace") if (p / "out.txt").exists() else ""
		stderr = (p / "err.txt").read_text(errors="replace") if (p / "err.txt").exists() else ""

		jobs[job_id] = {
			**jobs[job_id],
			"status": "finished",
			"stdout": stdout,
			"stderr": stderr,
			"compile_error": "",
			"isolate_diag": (r.stderr.strip() if r.stderr else ""),
		}

	except Exception as e:
		jobs[job_id] = {**jobs[job_id], "status": "failed", "error": str(e)}
	finally:
		isolate_cleanup(box_id)


def worker_loop(box_id: int) -> None:
	while True:
		item = job_queue.get()
		if item is None:
			break
		job_id, program = item
		jobs[job_id] = {**jobs[job_id], "status": "running", "box_id": box_id}
		run_job_in_box(box_id, job_id, program)


def start_workers() -> None:
	init_mp()
	for box_id in range(WORKERS):
		p = _ctx.Process(target=worker_loop, args=(box_id,), daemon=True)
		p.start()
		_worker_processes.append(p)

def stop_workers() -> None:
	global manager

	if job_queue is not None:
		for _ in range(len(_worker_processes) or WORKERS):
			try:
				job_queue.put_nowait(None)
			except Full:
				job_queue.put(None)

	for p in _worker_processes:
		if p.is_alive():
			p.join(timeout=5)

	_worker_processes.clear()

	if manager is not None:
		manager.shutdown()
		manager = None


def submit_job(code: str, stdin: Optional[str]) -> tuple[str, str]:
	job_id = str(uuid.uuid4())
	jobs[job_id] = {"status": "queued"}

	payload: dict[str, Any] = {"code": code, "stdin": stdin}
	try:
		job_queue.put_nowait((job_id, payload))
	except Full:
		jobs.pop(job_id, None)
		raise

	return job_id, "queued"


def get_job(job_id: str) -> Optional[dict[str, Any]]:
	if job_id not in jobs:
		return None
	return dict(jobs[job_id])
