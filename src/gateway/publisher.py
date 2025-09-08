from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .bridge import ArduinoBridge, now_ms


def make_topic(prefix: str, gateway_id: str, kind: str, sensor_id: str) -> str:
    # p. ej. fleet/truck-01/telemetry/ambiente1
    parts = [p for p in [prefix, gateway_id, kind, sensor_id] if p]
    return "/".join(parts)


def telemetry_payload(
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


def health_gateway_payload(
    gateway_id: str,
    ts_ms: int,
    ip: Optional[str] = None,
    radio: Optional[str] = None,
    rssi: Optional[int] = None,
) -> Dict[str, Any]:
    obj: Dict[str, Any] = {
        "schema": "v1",
        "gateway_id": gateway_id,
        "ts": ts_ms,
        "health": {
            "pid": os.getpid(),
            "uptime_ms": ts_ms,
        },
    }
    if ip:    obj["health"]["ip"] = ip
    if radio: obj["health"]["radio"] = radio
    if rssi is not None: obj["health"]["rssi"] = rssi
    return obj


class HealthPublisher(threading.Thread):
    """
    Publica un latido periódico vía ArduinoBridge (modo por líneas).
    No usa atributo ._stop (para no romper threading tras fork).
    """

    def __init__(self, bridge: ArduinoBridge, topic: str, interval_s: int = 30):
        self.bridge = bridge
        self.topic = topic
        self.interval_s = max(5, int(interval_s))
        self.stop_evt = threading.Event()
        self._th = threading.Thread(target=self._loop, daemon=True, name="HEALTH")

    def start(self):
        self._th.start()

    def stop(self):
        self.stop_evt.set()
        self._th.join(timeout=2)

    def _loop(self):
        while not self.stop_evt.is_set():
            ts = now_ms()
            payload = health_gateway_payload("truck-01", ts)
            text = json.dumps(payload, separators=(",", ":"))
            # Ahora enviamos el payload completo (con llave de cierre)
            ok = self.bridge.publish_lines(self.topic, text)
            print("[HEALTH]", "OK" if ok else "ERR", flush=True)

            # backoff básico si falla
            delay = self.interval_s if ok else min(self.interval_s * 2, 120)
            for _ in range(int(delay * 10)):
                if self.stop_evt.is_set():
                    break
                time.sleep(0.1)
