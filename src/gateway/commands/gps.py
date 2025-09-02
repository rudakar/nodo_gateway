""" Comando para probar la funcionalidad GPS del módulo SIM7070G a través del Arduino."""

import logging
from gateway.bridge import ArduinoBridge
from gateway.configuration.config_loader import load_config

logger = logging.getLogger(__name__)

def execute_gps_test():
    """Envía un comando para obtener la posición GPS actual y mostrar la respuesta."""
    cfg = load_config("config.yaml")
    bridge = ArduinoBridge(cfg.gateway.serial_port, cfg.gateway.serial_baud)
    logging.info(bridge.get_gps())
    bridge.close()
