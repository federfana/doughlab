"""Server di uso quotidiano: certificati locali, agente di avvio e certificato della CA."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from doughlab import serve

from .test_diary import run_with_db


def test_subject_alt_names_cover_localhost_hostname_and_lan_ip() -> None:
    assert serve.subject_alt_names("pizza.local", "192.168.1.9") == (
        "DNS:localhost,DNS:pizza.local,IP:127.0.0.1,IP:192.168.1.9"
    )
    assert serve.subject_alt_names("pizza.local", "127.0.0.1").count("127.0.0.1") == 1


def test_launch_agent_runs_the_service_at_login_and_keeps_it_alive(tmp_path: Path) -> None:
    plist = serve.launch_agent_plist("/venv/bin/python", tmp_path, tmp_path / "s.log", {"DOUGHLAB_PORT": "8010"})

    assert plist["ProgramArguments"] == ["/venv/bin/python", "-m", "doughlab.serve", "run"]
    assert plist["RunAtLoad"] is True and plist["KeepAlive"] is True
    assert plist["WorkingDirectory"] == str(tmp_path)
    assert plist["EnvironmentVariables"]["DOUGHLAB_PORT"] == "8010"


def test_launch_agent_can_keep_the_mac_awake_only_when_asked(tmp_path: Path) -> None:
    plain = serve.launch_agent_plist("/venv/bin/python", tmp_path, tmp_path / "s.log", {})
    awake = serve.launch_agent_plist("/venv/bin/python", tmp_path, tmp_path / "s.log", {}, keep_awake=True)

    assert plain["ProgramArguments"][0] == "/venv/bin/python"
    assert awake["ProgramArguments"] == [
        "/usr/bin/caffeinate", "-i", "-s", "/venv/bin/python", "-m", "doughlab.serve", "run"]


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl non disponibile")
def test_cert_problem_detects_a_changed_ip_or_name_and_an_expiring_certificate(tmp_path: Path) -> None:
    serve.ensure_certs(tmp_path, hostname="pizza.local", ip="192.168.1.55")
    cert = tmp_path / "server.crt"

    assert serve.cert_problem(cert, "pizza.local", "192.168.1.55") is None
    assert "IP" in (serve.cert_problem(cert, "pizza.local", "192.168.1.5") or "")  # .5 non è un prefisso di .55
    assert "nome" in (serve.cert_problem(cert, "altro.local", "192.168.1.55") or "")
    assert serve.cert_problem(cert, "pizza.local", "192.168.1.55", min_days=900) == "in scadenza"
    assert serve.cert_problem(tmp_path / "manca.crt", "pizza.local", "192.168.1.55") is None


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl non disponibile")
def test_refresh_certs_regenerates_for_the_new_ip_but_not_without_a_network(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(serve, "CERT_DIR", tmp_path)
    monkeypatch.setattr(serve, "CA_CERT", tmp_path / "doughlab-ca.crt")
    monkeypatch.setattr(serve, "CA_KEY", tmp_path / "doughlab-ca.key")
    monkeypatch.setattr(serve, "SERVER_CERT", tmp_path / "server.crt")
    monkeypatch.setattr(serve, "SERVER_KEY", tmp_path / "server.key")
    monkeypatch.setattr(serve, "local_hostname", lambda: "pizza.local")
    original = serve.ensure_certs
    monkeypatch.setattr(serve, "ensure_certs", lambda hostname=None, ip=None: original(tmp_path, hostname, ip))
    original(tmp_path, hostname="pizza.local", ip="192.168.1.55")

    monkeypatch.setattr(serve, "local_ip", lambda: "192.168.1.55")
    assert serve.refresh_certs() is None
    monkeypatch.setattr(serve, "local_ip", lambda: "127.0.0.1")  # niente rete: non si tocca nulla
    assert serve.refresh_certs() is None
    monkeypatch.setattr(serve, "local_ip", lambda: "192.168.68.72")
    assert "IP" in (serve.refresh_certs() or "")
    assert serve.refresh_certs() is None  # ora il certificato corrisponde
    assert serve.cert_problem(tmp_path / "server.crt", "pizza.local", "192.168.68.72") is None


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl non disponibile")
def test_server_certificate_is_signed_by_the_local_ca_and_the_ca_is_reused(tmp_path: Path) -> None:
    ca = serve.ensure_certs(tmp_path, hostname="pizza.local", ip="192.168.1.9")
    first_ca = ca.read_bytes()
    verify = subprocess.run(
        ["openssl", "verify", "-CAfile", str(ca), str(tmp_path / "server.crt")], capture_output=True, text=True
    )
    text = subprocess.run(
        ["openssl", "x509", "-in", str(tmp_path / "server.crt"), "-noout", "-text"], capture_output=True, text=True
    ).stdout

    assert verify.returncode == 0, verify.stderr
    assert "DNS:pizza.local" in text and "IP Address:192.168.1.9" in text
    assert serve.ensure_certs(tmp_path, hostname="pizza.local", ip="192.168.1.10").read_bytes() == first_ca
    assert sorted(p.name for p in tmp_path.iterdir() if p.suffix in {".cnf", ".csr"}) == []


def test_ca_certificate_is_served_for_the_phone_only_when_it_exists(tmp_path: Path, monkeypatch) -> None:
    ca = tmp_path / "doughlab-ca.crt"

    async def check(client: AsyncClient, sessions: async_sessionmaker) -> None:
        assert (await client.get("/ca.crt")).status_code == 404
        ca.write_text("-----BEGIN CERTIFICATE-----\nabc\n-----END CERTIFICATE-----\n")
        response = await client.get("/ca.crt")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-x509-ca-cert")
        assert "doughlab-ca.crt" in response.headers["content-disposition"]

    monkeypatch.setattr("doughlab.main.CA_CERT", ca)
    run_with_db(tmp_path, monkeypatch, check)


def test_extra_hostnames_are_added_once() -> None:
    names = serve.subject_alt_names("pizza.local", "192.168.1.9", "mac.home", "PIZZA.local", "")

    assert names == "DNS:localhost,DNS:pizza.local,IP:127.0.0.1,DNS:mac.home,IP:192.168.1.9"
