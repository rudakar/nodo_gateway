import logging
from gateway.bridge import ArduinoBridge
from gateway.configuration.config_loader import load_config

logger = logging.getLogger(__name__)

def execute_at_testing(cmd: str):
    """Envía un AT al Arduino/SIM7070G y muestra la respuesta."""
    cfg = load_config("config.yaml")
    bridge = ArduinoBridge(cfg.gateway.serial_port, cfg.gateway.serial_baud)
    logging.info(bridge.send_at(cmd))
    bridge.close()
