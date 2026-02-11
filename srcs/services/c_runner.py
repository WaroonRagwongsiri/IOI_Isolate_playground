from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from queue import Full

from ..controllers import c_controller

router = APIRouter(tags=["c"])


class CProgram(BaseModel):
	code: str
	stdin: Optional[str] = None


@router.get("/")
def test_connection():
	return "Connected"


@router.post("/run_c")
def submit_c(program: CProgram):
	try:
		job_id, status = c_controller.submit_job(program.code, program.stdin)
	except Full:
		raise HTTPException(429, "Server queue is full")
	return {"job_id": job_id, "status": status}


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
	job = c_controller.get_job(job_id)
	if job is None:
		raise HTTPException(404, "Job not found")
	return job
