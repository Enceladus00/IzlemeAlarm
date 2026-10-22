from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.api.routes.alerts import router as alerts_router
from backend.api.routes.analysis import router as analysis_router
from backend.api.routes.rules import router as rules_router
from backend.api.routes.transactions import router as transactions_router
from backend.api.routes.uploads import router as uploads_router


load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def create_app() -> FastAPI:
    application = FastAPI(
        title="İşlem İzleme ve Alarm Sistemi",
        description="Transaction monitoring MVP API.",
        version="0.2.0",
    )
    application.include_router(analysis_router)
    application.include_router(alerts_router)
    application.include_router(rules_router)
    application.include_router(transactions_router)
    application.include_router(uploads_router)

    @application.exception_handler(RuntimeError)
    def runtime_error_handler(_request: Any, exc: RuntimeError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    return application


app = create_app()
