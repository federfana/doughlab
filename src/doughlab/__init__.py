"""DoughLab — un laboratorio digitale per impasti."""

__version__ = "0.1.0"


def main() -> None:
    """Entry point del comando `doughlab`: avvia il server di sviluppo."""
    from pathlib import Path

    import uvicorn

    from .config import settings

    uvicorn.run(
        "doughlab.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        reload_dirs=[str(Path(__file__).parent)],  # senza, anche tests/ riavvia il server
    )
