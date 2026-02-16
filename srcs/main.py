from fastapi import FastAPI

from .controllers.c_controller import start_workers, stop_workers
from .services.c_runner import router as c_router

app = FastAPI()
app.include_router(c_router)

@app.on_event("startup")
def on_startup():
	start_workers()

@app.on_event("shutdown")
def on_end():
	stop_workers()