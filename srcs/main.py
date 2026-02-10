import subprocess
import uuid
from pathlib import Path
from multiprocessing import Process, Queue, Manager
from queue import Full
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

ISOLATE = "isolate"
CC = "cc"

WORKERS = 4
JOB_QUEUE_MAX = 200

job_queue: Queue = Queue(maxsize=JOB_QUEUE_MAX)
manager = Manager()
jobs = manager.dict()


class CProgram(BaseModel):
	code: str
	stdin: Optional[str] = None


def box_path(box_id: int) -> Path:
	return Path(f"/var/local/lib/isolate/{box_id}/box")


def isolate_init(box_id: int) -> None:
	# Defensive cleanup, then init
	subprocess.run([ISOLATE, f"--box-id={box_id}", "--cleanup"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
	r = subprocess.run([ISOLATE, f"--box-id={box_id}", "--init"], capture_output=True, text=True)
	if r.returncode != 0:
		raise RuntimeError(r.stderr.strip() or "isolate init failed")


def isolate_cleanup(box_id: int) -> None:
	subprocess.run([ISOLATE, f"--box-id={box_id}", "--cleanup"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_job_in_box(box_id: int, job_id: str, program: dict) -> None:
	try:
		isolate_init(box_id)
		p = box_path(box_id)

		# Write inputs into this box
		(p / "main.c").write_text(program["code"], encoding="utf-8")
		if program.get("stdin") is not None:
			(p / "input.txt").write_text(program["stdin"], encoding="utf-8")

		# Compile OUTSIDE isolate, but compile INTO the box using absolute paths
		compile_cmd = [
			CC,
			str(p / "main.c"),
			"-std=c11",
			"-O2",
			"-o",
			str(p / "main"),
		]
		c = subprocess.run(compile_cmd, capture_output=True, text=True)

		if c.returncode != 0:
			jobs[job_id] = {
				**jobs[job_id],
				"status": "failed",
				"error": c.stderr.strip(),
			}
			return

		# Ensure binary exists in the box
		if not (p / "main").exists():
			jobs[job_id] = {
				**jobs[job_id],
				"status": "failed",
				"error": "compile failed: output binary not found",
			}
			return

		# Run inside isolate (CWD is /box, so ./main resolves)
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
		run_cmd += ["--run", "--", "./main"]

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
		item = job_queue.get()  # blocking
		if item is None:
			break
		job_id, program = item
		# Update state
		jobs[job_id] = {**jobs[job_id], "status": "running", "box_id": box_id}
		run_job_in_box(box_id, job_id, program)


def start_workers() -> None:
	for box_id in range(WORKERS):
		p = Process(target=worker_loop, args=(box_id,), daemon=True)
		p.start()


@app.on_event("startup")
def on_startup():
	start_workers()


@app.get("/")
def test_connection():
	return "Connected"


@app.post("/run_c")
def submit_c(program: CProgram):
	job_id = str(uuid.uuid4())
	jobs[job_id] = {"status": "queued"}

	try:
		job_queue.put_nowait((job_id, program.model_dump()))
	except Full:
		jobs.pop(job_id, None)
		raise HTTPException(429, "Server queue is full")

	return {"job_id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}")
def job_status(job_id: str):
	if job_id not in jobs:
		raise HTTPException(404, "Job not found")
	return dict(jobs[job_id])
