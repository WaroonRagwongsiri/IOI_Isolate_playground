import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

BOX_ID = 0
BOX_PATH = Path(f"/var/local/lib/isolate/{BOX_ID}/box")
ISOLATE = "isolate"

CC = "cc"


class CProgram(BaseModel):
	code: str
	stdin: str | None = None

@app.get("/")
def test_connection():
	return "Connected"

@app.post("/create_box")
def create_box():
	subprocess.run(
		[ISOLATE, f"--box-id={BOX_ID}", "--cleanup"],
		stdout=subprocess.DEVNULL,
		stderr=subprocess.DEVNULL,
	)
	r = subprocess.run([ISOLATE, "--init"], capture_output=True, text=True)
	if r.returncode != 0:
		raise HTTPException(500, r.stderr)
	return {"box_id": BOX_ID}


@app.post("/run_c")
def run_c(program: CProgram):
	BOX_PATH.mkdir(parents=True, exist_ok=True)

	# write C file
	(BOX_PATH / "main.c").write_text(program.code)

	# optional stdin
	if program.stdin is not None:
		(BOX_PATH / "input.txt").write_text(program.stdin)

	# compile inside isolate
	compile_cmd = [
		CC,
		str(BOX_PATH / "main.c"),
		"-std=c11",
		"-o",
		str(BOX_PATH / "main"),
	]

	c = subprocess.run(compile_cmd, capture_output=True, text=True)
	if c.returncode != 0:
		return {"compile_error": c.stderr}

	# run inside isolate
	run_cmd = [
		ISOLATE,
		f"--box-id={BOX_ID}",
		"--time=1",
		"--mem=262144",
		"--stdout=out.txt",
		"--stderr=err.txt",
	]

	if program.stdin is not None:
		run_cmd.append("--stdin=input.txt")

	run_cmd += ["--run", "--", "./main"]

	subprocess.run(run_cmd)

	stdout = (BOX_PATH / "out.txt").read_text(errors="replace") if (BOX_PATH / "out.txt").exists() else ""
	stderr = (BOX_PATH / "err.txt").read_text(errors="replace") if (BOX_PATH / "err.txt").exists() else ""

	return {
		"stdout": stdout,
		"stderr": stderr,
	}
