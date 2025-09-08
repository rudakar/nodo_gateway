""" Comando para publicar un mensaje de prueba vía MQTT a través del Arduino/SIM7070G."""
from gateway.bridge import ArduinoBridge
from gateway.configuration.config_loader import load_config
import logging

logger = logging.getLogger(__name__)


def execute_publish_test(topic: str, payload: str):
    """ Publica un JSON (el Arduino añade la última llave '}' sólo si usas el modo por líneas)."""
    cfg = load_config("config.yaml")
    bridge = ArduinoBridge(cfg.gateway.serial_port, cfg.gateway.serial_baud)
    ok = bridge.publish_lines(topic, payload)
    logger.info("%s -> %s", "OK" if ok else "ERR", topic)
    bridge.close()
