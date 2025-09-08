"""Comando para probar el nuevo protocolo de health <<<HEALTH_TS>>> + timestamp."""

import time
import logging
from gateway.bridge import ArduinoBridge
from gateway.configuration.config_loader import load_config

logger = logging.getLogger(__name__)

def execute_health_test():
    """Prueba el nuevo comando de health que retorna datos CPSI."""
    cfg = load_config("config.yaml")
    bridge = ArduinoBridge(cfg.gateway.serial_port, cfg.gateway.serial_baud)
    
    try:
        timestamp = int(time.time() * 1000)
        logger.info(f"Enviando comando health con timestamp: {timestamp}")
        
        response = bridge.send_health_command(timestamp, read_timeout=15.0)
        
        if response.strip():
            logger.info("Respuesta del comando health:")
            logger.info(response)
            
            # Intentar parsear datos CPSI
            lines = response.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line and ',' in line and not line.startswith('{'):
                    parts = line.split(',')
                    if len(parts) >= 5:
                        logger.info(f"Datos CPSI parseados - SINR:{parts[0]}, RSRP:{parts[1]}, Tipo:{parts[2]}, GCI:{parts[3]}, TAC:{parts[4]}")
        else:
            logger.warning("No se recibió respuesta del comando health")
            
    except Exception as e:
        logger.error(f"Error ejecutando health test: {e}")
    finally:
        bridge.close()
