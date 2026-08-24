from fastapi import FastAPI

from fast_api_test_app.routers.tasks_routers import router as tasks_router


app = FastAPI(title="FastAPI Task API")
app.include_router(tasks_router)

