"""DoughLab — un laboratorio digitale per impasti."""

__version__ = "0.1.0"


def main() -> None:
    """Entry point del comando `doughlab`: avvia il server di sviluppo."""
    import uvicorn

    uvicorn.run(
        "doughlab.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
