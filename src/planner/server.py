import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.planner.api.auth_middleware import create_token_dependency
from src.planner.api.health import router as health_router
from src.planner.api import auth as auth_module
from src.planner.api import preferences as prefs_module
from src.planner.api import schedule as schedule_module
from src.planner.db import PlannerDB
from src.planner.ingestion.google_auth import GoogleAuthManager

STATIC_DIR = Path(__file__).parent.parent.parent / "frontend" / "dist"


def create_app(
    db_path: str | None = None,
    auth_token: str | None = None,
    static_dir: Path | None = None,
    google_client_config: dict | None = None,
) -> FastAPI:
    if auth_token is None:
        auth_token = secrets.token_urlsafe(32)

    app = FastAPI(title="Productivity Planner")
    app.state.auth_token = auth_token

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    require_token = create_token_dependency(auth_token)

    if db_path is None:
        from src.utils.constants import APP_DATA_DIR
        db_path = str(Path(APP_DATA_DIR) / "planner.db")

    db = PlannerDB(db_path)
    db.initialize()

    def get_db() -> PlannerDB:
        return db

    app.dependency_overrides[prefs_module.get_db] = get_db
    app.dependency_overrides[schedule_module.get_db] = get_db

    # Google OAuth setup
    if google_client_config:
        auth_module.auth_manager = GoogleAuthManager(
            client_config=google_client_config,
            redirect_uri=f"http://localhost:8321/auth/callback",
        )

    app.dependency_overrides[auth_module.get_db] = get_db

    # Protected auth routes (bearer token required)
    for route in auth_module.router.routes:
        route.dependencies = [require_token]
    app.include_router(auth_module.router)

    # Callback route (unauthenticated — Google redirects browser here)
    app.include_router(auth_module.callback_router)

    app.include_router(health_router)

    for route in prefs_module.router.routes:
        route.dependencies = [require_token]
    app.include_router(prefs_module.router)

    for route in schedule_module.router.routes:
        route.dependencies = [require_token]
    app.include_router(schedule_module.router)

    serve_dir = static_dir or STATIC_DIR
    if serve_dir.exists():
        index_path = serve_dir / "index.html"

        @app.get("/")
        def serve_index():
            html = index_path.read_text()
            html = html.replace("__TOKEN_PLACEHOLDER__", auth_token)
            return HTMLResponse(html)

        app.mount("/", StaticFiles(directory=str(serve_dir), html=False), name="static")

    @app.on_event("shutdown")
    def shutdown():
        db.close()

    return app


def run_server(db_path: str, auth_token: str, host: str = "127.0.0.1", port: int = 8321):
    """Entry point for subprocess launch."""
    import uvicorn

    app = create_app(db_path=db_path, auth_token=auth_token)
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    import sys

    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    auth_token = sys.argv[2] if len(sys.argv) > 2 else None
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 8321
    run_server(db_path=db_path, auth_token=auth_token, port=port)
