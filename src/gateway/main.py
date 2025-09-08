""" main CLI commands and entry point. """

from __future__ import annotations
import asyncio
import typer
from gateway.commands.at import execute_at_testing
from gateway.commands.diag import execute_diagnostic
from gateway.commands.gps import execute_gps_test
from gateway.commands.pub import execute_publish_test
from gateway.commands.health import execute_health_test
from gateway.commands.run import run
from gateway.configuration.logging_loader import configure_logging

app = typer.Typer(help="Gateway BLE/BLUNO -> SQLite + Arduino SIM7070 MQTT")
configure_logging()

@app.command("run")
def cmd_run():
    """Arranca el gateway (BLE/BLUNO -> SQLite + MQTT via Arduino)."""
    run()


@app.command("at")
def cmd_at(cmd: str):
    """Envía un AT al Arduino/SIM7070G y muestra la respuesta."""
    execute_at_testing(cmd)


@app.command("gps")
def cmd_gps():
    """Pide un fix GPS (o fallback Pamplona) al Arduino."""
    execute_gps_test()


@app.command("pub")
def cmd_pub(topic: str, payload: str):
    """
    Publica un JSON (el Arduino añade la última llave '}' sólo si usas el modo por líneas).
    Ej: gateway pub fleet/truck-01/test '{"ping":"ok"}'
    """
    execute_publish_test(topic, payload)


@app.command("health")
def cmd_health():
    """Prueba el nuevo comando de health que retorna datos CPSI."""
    execute_health_test()


@app.command("diag")
def cmd_diag():
    """Ejecuta diagnóstico completo del módulo SIM7070."""
    execute_diagnostic()

def main():
    """ Entrypoint principal. """
    app()


if __name__ == "__main__":
    main()
