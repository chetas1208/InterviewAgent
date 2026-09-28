from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(
        title="Hypersmell",
        description="Scent memory platform for fragrance professionals",
        version="0.1.0",
    )

    from hypersmell.api.router import api_router

    app.include_router(api_router, prefix="/api")

    @app.get("/status")
    def health_check():
        return {"status": "ok"}

    import inngest.fast_api

    from hypersmell.tasks.client import client
    from hypersmell.tasks.handlers import fn_process_resource, sync_integration

    inngest.fast_api.serve(
        app,
        client,
        [sync_integration, fn_process_resource],
    )

    return app


app = create_app()
