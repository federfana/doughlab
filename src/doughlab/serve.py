"""Uso quotidiano: server senza reload (HTTP + HTTPS), certificati locali e avvio automatico su macOS."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import re
import plistlib
import shutil
import signal
import socket
import subprocess
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import uvicorn

from .config import DATA_DIR, ROOT_DIR, settings

PROJECT_DIR = ROOT_DIR.parent.parent
CERT_DIR = DATA_DIR / "certs"
CA_CERT = CERT_DIR / "doughlab-ca.crt"
CA_KEY = CERT_DIR / "doughlab-ca.key"
SERVER_CERT = CERT_DIR / "server.crt"
SERVER_KEY = CERT_DIR / "server.key"

AGENT_LABEL = "it.doughlab.server"
AGENT_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{AGENT_LABEL}.plist"
LOG_FILE = Path.home() / "Library" / "Logs" / "DoughLab" / "server.log"
# Apple rifiuta certificati server validi più di 825 giorni: margine per sicurezza.
SERVER_CERT_DAYS = 800
CA_DAYS = 3650
# Il certificato si rigenera da solo quando manca meno di questo alla scadenza.
CERT_RENEW_DAYS = 60
NETWORK_CHECK_SECONDS = 60


def local_ip() -> str:
    """Indirizzo del Mac sulla rete locale (nessun pacchetto viene inviato)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("192.0.2.1", 9))
            return str(probe.getsockname()[0])
        except OSError:
            return "127.0.0.1"


def local_hostname() -> str:
    """Nome `.local` del Mac, raggiungibile dal telefono sulla stessa rete."""
    try:
        name = subprocess.run(
            ["scutil", "--get", "LocalHostName"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        name = socket.gethostname().split(".")[0]
    return f"{name}.local"


def subject_alt_names(hostname: str, ip: str, *extra_hosts: str) -> str:
    names = ["DNS:localhost", f"DNS:{hostname}", "IP:127.0.0.1"]
    names += [f"DNS:{host}" for host in extra_hosts if host and host.lower() != hostname.lower()]
    if ip != "127.0.0.1":
        names.append(f"IP:{ip}")
    return ",".join(names)


def _openssl(*args: str) -> None:
    binary = shutil.which("openssl")
    if binary is None:
        raise SystemExit("openssl non trovato: serve per creare i certificati.")
    subprocess.run([binary, *args], check=True, capture_output=True)


def ensure_certs(cert_dir: Path = CERT_DIR, hostname: str | None = None, ip: str | None = None) -> Path:
    """Crea (una volta) la CA locale e rigenera il certificato del server; restituisce la CA da installare."""
    hostname = hostname or local_hostname()
    ip = ip or local_ip()
    cert_dir.mkdir(parents=True, exist_ok=True)
    ca_cert, ca_key = cert_dir / CA_CERT.name, cert_dir / CA_KEY.name
    server_cert, server_key = cert_dir / SERVER_CERT.name, cert_dir / SERVER_KEY.name
    ca_conf, server_conf, server_csr = (cert_dir / name for name in ("ca.cnf", "server.cnf", "server.csr"))
    try:
        if not (ca_cert.exists() and ca_key.exists()):
            ca_conf.write_text(
                "[req]\ndistinguished_name=dn\nprompt=no\nx509_extensions=ext\n"
                "[dn]\nCN=DoughLab (rete locale)\n"
                "[ext]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n"
                "subjectKeyIdentifier=hash\n"
            )
            _openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-sha256", "-days", str(CA_DAYS),
                     "-keyout", str(ca_key), "-out", str(ca_cert), "-config", str(ca_conf))
            ca_key.chmod(0o600)
        server_conf.write_text(
            "basicConstraints=CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n"
            f"extendedKeyUsage=serverAuth\nsubjectAltName={subject_alt_names(hostname, ip, socket.gethostname())}\n"
        )
        _openssl("req", "-new", "-newkey", "rsa:2048", "-nodes", "-keyout", str(server_key),
                 "-out", str(server_csr), "-subj", f"/CN={hostname}")
        server_key.chmod(0o600)
        _openssl("x509", "-req", "-in", str(server_csr), "-CA", str(ca_cert), "-CAkey", str(ca_key),
                 "-CAcreateserial", "-out", str(server_cert), "-days", str(SERVER_CERT_DAYS),
                 "-sha256", "-extfile", str(server_conf))
    finally:
        for leftover in (ca_conf, server_conf, server_csr):
            leftover.unlink(missing_ok=True)
    return ca_cert


def cert_problem(cert: Path, hostname: str, ip: str, min_days: int = CERT_RENEW_DAYS) -> str | None:
    """Perché il certificato non va più bene (IP o nome cambiati, in scadenza), oppure None."""
    binary = shutil.which("openssl")
    if binary is None or not cert.exists():
        return None
    shown = subprocess.run(
        [binary, "x509", "-in", str(cert), "-noout", "-ext", "subjectAltName"], capture_output=True, text=True
    )
    if shown.returncode != 0:
        return "non leggibile"
    names = {part.strip().lower() for part in re.split(r"[,\n]", shown.stdout)}
    if f"ip address:{ip}" not in names:
        return f"l'IP del Mac è cambiato ({ip})"
    if f"dns:{hostname}".lower() not in names:
        return f"il nome del Mac è cambiato ({hostname})"
    expiring = subprocess.run([binary, "x509", "-in", str(cert), "-noout", "-checkend", str(min_days * 86400)],
                              capture_output=True)
    return "in scadenza" if expiring.returncode != 0 else None


def refresh_certs() -> str | None:
    """Rigenera il certificato se non corrisponde più alla rete; restituisce il motivo, oppure None.

    Senza rete (solo 127.0.0.1) non fa nulla: un certificato senza l'IP della LAN sarebbe peggiore.
    """
    if https_files() is None:
        return None
    ip = local_ip()
    if ip == "127.0.0.1":
        return None
    hostname = local_hostname()
    problem = cert_problem(SERVER_CERT, hostname, ip)
    if problem:
        ensure_certs(hostname=hostname, ip=ip)
    return problem


def https_files() -> tuple[Path, Path] | None:
    return (SERVER_CERT, SERVER_KEY) if SERVER_CERT.exists() and SERVER_KEY.exists() else None


class _Server(uvicorn.Server):
    """Due server nello stesso processo: i segnali li gestisce `serve`, non uvicorn."""

    @contextlib.contextmanager
    def capture_signals(self) -> Iterator[None]:
        yield


async def _serve(host: str, port: int, https_port: int) -> None:
    http = _Server(uvicorn.Config("doughlab.main:app", host=host, port=port))
    tasks = [asyncio.create_task(http.serve())]
    while not http.started and not tasks[0].done():
        await asyncio.sleep(0.1)
    servers = [http]
    certs = https_files()
    if certs and not tasks[0].done():
        # Il ciclo di vita dell'app (DB, farine) è già stato eseguito dal server HTTP.
        https = _Server(uvicorn.Config(
            "doughlab.main:app", host=host, port=https_port, lifespan="off",
            ssl_certfile=str(certs[0]), ssl_keyfile=str(certs[1]),
        ))
        servers.append(https)
        tasks.append(asyncio.create_task(https.serve()))

    def stop() -> None:
        for server in servers:
            server.should_exit = True

    async def watch_network() -> None:
        # Se la rete cambia mentre il server è acceso, si esce: launchd lo riavvia con il certificato nuovo.
        while True:
            await asyncio.sleep(NETWORK_CHECK_SECONDS)
            problem = await asyncio.to_thread(refresh_certs)
            if problem:
                print(f"Certificato HTTPS rigenerato ({problem}): riavvio del server.")
                stop()
                return

    watcher = asyncio.create_task(watch_network()) if certs else None

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop)
    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    stop()
    if watcher is not None:
        watcher.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    for task in done:
        task.result()


def run() -> None:
    problem = refresh_certs()
    if problem:
        print(f"Certificato HTTPS rigenerato ({problem}). Se il telefono non si collega, controlla l'indirizzo.")
    asyncio.run(_serve(settings.host, settings.port, settings.https_port))


def launch_agent_plist(
    python: str, project_dir: Path, log_file: Path, env: dict[str, str], keep_awake: bool = False
) -> dict[str, Any]:
    # caffeinate -i -s: il Mac non va in stop per inattività finché il server è acceso (-s solo con alimentatore).
    awake = ["/usr/bin/caffeinate", "-i", "-s"] if keep_awake else []
    return {
        "Label": AGENT_LABEL,
        "ProgramArguments": [*awake, python, "-m", "doughlab.serve", "run"],
        "WorkingDirectory": str(project_dir),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "StandardOutPath": str(log_file),
        "StandardErrorPath": str(log_file),
        "EnvironmentVariables": {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin", **env},
    }


def _launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _port_busy(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def install_agent(keep_awake: bool = False) -> None:
    env = {k: v for k, v in os.environ.items() if k.startswith("DOUGHLAB_")}
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    AGENT_PLIST.parent.mkdir(parents=True, exist_ok=True)
    with AGENT_PLIST.open("wb") as handle:
        plistlib.dump(launch_agent_plist(sys.executable, PROJECT_DIR, LOG_FILE, env, keep_awake), handle)
    _launchctl("bootout", f"{_domain()}/{AGENT_LABEL}")
    if _port_busy(settings.port):
        print(f"Installato, ma la porta {settings.port} è occupata (server di sviluppo acceso?): "
              "partirà al prossimo accesso, oppure ferma l'altro server e rilancia `install`.")
        return
    result = _launchctl("bootstrap", _domain(), str(AGENT_PLIST))
    if result.returncode != 0:
        raise SystemExit(f"launchctl bootstrap non riuscito: {result.stderr.strip()}")
    awake = " Il Mac non andrà in stop per inattività (con alimentatore)." if keep_awake else ""
    print(f"Server avviato (porta {settings.port}) e attivo a ogni accesso.{awake} Log: {LOG_FILE}")


def uninstall_agent() -> None:
    _launchctl("bootout", f"{_domain()}/{AGENT_LABEL}")
    AGENT_PLIST.unlink(missing_ok=True)
    print("Avvio automatico rimosso.")


def cli(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="doughlab-service", description=__doc__)
    parser.add_argument(
        "command", nargs="?", default="run",
        choices=["run", "cert", "install", "uninstall", "restart", "status"],
        help="run: avvia il server; cert: crea i certificati HTTPS; install/uninstall: avvio "
             "automatico all'accesso; restart: riavvia il servizio (dopo un aggiornamento)",
    )
    parser.add_argument(
        "--keep-awake", action="store_true",
        help="con install: impedisce lo stop del Mac per inattività finché il server è acceso (alimentatore collegato)",
    )
    args = parser.parse_args(argv)
    command = args.command
    if command == "run":
        run()
    elif command == "cert":
        ca = ensure_certs()
        print(f"Certificato del server rigenerato per {local_hostname()} e {local_ip()}.")
        print(f"Certificato da installare sul telefono: {ca}")
        print(f"Oppure, dal telefono: http://{local_ip()}:{settings.port}/ca.crt")
        print(f"Poi apri: https://{local_ip()}:{settings.https_port} (o https://{local_hostname()}:{settings.https_port})")
    elif command == "install":
        install_agent(args.keep_awake)
    elif command == "uninstall":
        uninstall_agent()
    elif command == "restart":
        result = _launchctl("kickstart", "-k", f"{_domain()}/{AGENT_LABEL}")
        print("Riavviato." if result.returncode == 0 else f"Non riuscito: {result.stderr.strip()}")
    else:
        result = _launchctl("print", f"{_domain()}/{AGENT_LABEL}")
        print("Attivo." if result.returncode == 0 else "Non attivo.")


if __name__ == "__main__":
    cli()
