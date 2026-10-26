from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.api.routes.alerts import router as alerts_router
from backend.api.routes.auth import router as auth_router
from backend.api.routes.audit import router as audit_router
from backend.api.routes.analysis import router as analysis_router
from backend.api.routes.rules import router as rules_router
from backend.api.routes.transactions import router as transactions_router
from backend.api.routes.uploads import router as uploads_router
from backend.api.routes.users import router as users_router
from backend.security import get_jwt_secret


load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        get_jwt_secret()
        yield

    application = FastAPI(
        title="İşlem İzleme ve Alarm Sistemi",
        description="Transaction monitoring MVP API.",
        version="0.2.0",
        lifespan=lifespan,
    )
    application.include_router(auth_router)
    application.include_router(audit_router)
    application.include_router(analysis_router)
    application.include_router(alerts_router)
    application.include_router(rules_router)
    application.include_router(transactions_router)
    application.include_router(uploads_router)
    application.include_router(users_router)

    @application.exception_handler(RuntimeError)
    def runtime_error_handler(_request: Any, exc: RuntimeError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    return application


app = create_app()
