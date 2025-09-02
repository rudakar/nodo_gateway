from gateway.bridge import ArduinoBridge
from gateway.configuration.config_loader import load_config


def execute_diagnostic():
    """Ejecuta diagnóstico completo del módulo SIM7070."""
    cfg = load_config("config.yaml")
    bridge = ArduinoBridge(cfg.gateway.serial_port, cfg.gateway.serial_baud)
    try:
        print("=== DIAGNÓSTICO SIM7070 ===")
        print(bridge.send_direct_command("<<<DIAG>>>", read_timeout=30.0))
    finally:
        bridge.close()
