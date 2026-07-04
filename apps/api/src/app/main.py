from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.errors import register_error_handlers
from app.logging import setup_logging
from app.modules.auth.routes import router as auth_router
from app.modules.documents.routes import router as documents_router
from app.modules.knowledge.routes import router as knowledge_router
from app.modules.opportunities.routes import router as opportunities_router
from app.modules.pipelines.routes import router as pipelines_router
from app.modules.projects.routes import router as projects_router
from app.modules.retrieval.routes import router as retrieval_router


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validate_for_environment()
    setup_logging(settings.env)

    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.env)

    app = FastAPI(
        title="AI Transformation Copilot API",
        version="0.1.0",
        openapi_url="/v1/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)

    app.include_router(auth_router, prefix="/v1")
    app.include_router(projects_router, prefix="/v1")
    app.include_router(documents_router, prefix="/v1")
    app.include_router(pipelines_router, prefix="/v1")
    app.include_router(retrieval_router, prefix="/v1")
    app.include_router(knowledge_router, prefix="/v1")
    app.include_router(opportunities_router, prefix="/v1")

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
