""" Thread to sustain mqtt connection and publish data. """
import json
import logging
import queue
import threading
from typing import Any, Dict, Optional

from gateway.bridge import ArduinoBridge
from gateway.models import MQTTQueueItem
from gateway.sqlite.db import now_ms

logger = logging.getLogger(__name__)

class MQTTThread( threading.Thread ):
    """
    Hilo base para publicar los datos recibidos por los arduinos Bluno
    """

    def __init__(self, 
            mqtt_queue: queue.Queue[MQTTQueueItem], 
            bridge_at : ArduinoBridge,
            gateway_id: str = "1",
        ) -> None:

        super().__init__(daemon=True)
        self.mqtt_queue = mqtt_queue
        self.bridge = bridge_at
        self.gateway_id = gateway_id
        self.running = True

    def run(self):
        """ Iniciar el hilo de conexion a mqtt"""
        while self.running:
            try:
                item = self.mqtt_queue.get(timeout=1.0)
                if item:
                    logger.debug("Publicando item a mqtt: %s", item)
                    topic = f"fleet/1/telemetry/{item.sensor_id}"
                    ts_ms=now_ms()
                    payload = json.dumps(
                        {
                            "gas": int(item.gas),
                            "temp": round(item.temp, 2),
                            "sensor_id": item.sensor_id,
                            "gateway_id": self.gateway_id,
                        },
                    separators=(",", ":"),   # sin espacios
                    ensure_ascii=False       # por si hay UTF-8 en IDs
                    )
                    size_bytes = len(payload.encode("utf-8"))
                    logger.info("payload bytes: %d, payload: %s", size_bytes, payload)
                    self.bridge.publish_lines(topic, payload + "}", wait_ok=-4)
                    self.mqtt_queue.task_done()
                    logger.info("queue size: %d", self.mqtt_queue.qsize())
            except queue.Empty:
                continue

    def make_topic(self, prefix: str, gateway_id: str, kind: str, sensor_id: str) -> str:
        # p. ej. fleet/truck-01/telemetry/ambiente1
        parts = [p for p in [prefix, gateway_id, kind, sensor_id] if p]
        return "/".join(parts)


    def telemetry_payload(
        self,
        gateway_id: str,
        sensor_id: str,
        fields: Dict[str, Any],
        ts_ms: int,
        gps: Optional[Dict[str, Any]] = None,
        seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        obj: Dict[str, Any] = {
            "schema": "v1",
            "gateway_id": gateway_id,
            "sensor_id": sensor_id,
            "ts": ts_ms,
            "data": fields,
        }
        if gps:
            obj["gps"] = gps
        if seq is not None:
            obj["seq"] = seq
        return obj

    def stop(self):
        """ Detener el hilo de publicación a mqtt"""
        self.running = False
