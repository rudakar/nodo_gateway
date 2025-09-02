# src/gateway/bluno.py
""" Module to read from bluno devices via BLE """
from __future__ import annotations
from dataclasses import dataclass
import json
import logging
import queue
import threading
import time
from typing import Optional, Callable

from bluepy.btle import (
    Peripheral,
    DefaultDelegate,
    BTLEDisconnectError,
    BTLEException,
)

from gateway.configuration.config_loader import BlunoDevice
from gateway.models import MQTTQueueItem, SQLiteDatabaseItem
from gateway.sqlite.db import now_ms

logger = logging.getLogger(__name__)


@dataclass
class _ConnState:
    p: Optional[Peripheral] = None
    tx_char = None
    cmd_char = None
    cccd_handle: Optional[int] = None


class _LineDelegate(DefaultDelegate):
    """Acumula notificaciones y entrega líneas terminadas en \\n vía callback (no bloqueante)."""
    def __init__(self, name: str, on_line: Callable[[str], None]) -> None:
        super().__init__()
        self._name = name
        self._buf = bytearray()
        self._on_line = on_line

    def handleNotification(self, cHandle, data):  # noqa: N802
        self._buf.extend(data)
        while True:
            nl = self._buf.find(b"\n")
            if nl == -1:
                break
            line = self._buf[:nl].decode("utf-8", errors="ignore").strip()
            del self._buf[: nl + 1]
            if line:
                self._on_line(line)


class BlunoWorker(threading.Thread):
    """
    Un hilo por BLUNO:
      - reconecta indefinidamente (intervalo fijo)
      - inicializa (password + UART) si es posible
      - activa NOTIFY en TX_UUID
      - encola las notificaciones; sub-hilo 'tx' imprime/guarda
    """

    def __init__(self, 
        device: BlunoDevice, 
        mqtt_queue: queue.Queue[MQTTQueueItem], 
        db_queue: queue.Queue[SQLiteDatabaseItem]
    ) -> None:
        super().__init__(daemon=True, name=f"bluno-{device.name}")
        # Config proveniente del YAML/loader
        self.device_name = device.name
        self.address = device.address
        self.sensor_id = getattr(device, "sensor_id", "bluno")
        self.parse = getattr(device, "parse", "raw")
        self.field_map = getattr(device, "field_map", {}) or {}
        self.tx_uuid = device.tx_uuid
        self.command_uuid = device.command_uuid
        self.password_ascii = getattr(device, "password_ascii", None)
        self.uart_ascii = getattr(device, "uart_ascii", None)
        self.reconnect_interval = int(getattr(device, "reconnect_interval", 5))
        self.mqtt_queue = mqtt_queue
        self.db_queue = db_queue

        logger.info("BlunoWorker[%s] creado para %s (%s)", self.device_name, self.address, self.sensor_id)
        logger.info("  parse=%s field_map=%s", self.parse, self.field_map)
        logger.info("  tx_uuid=%s command_uuid=%s", self.tx_uuid, self.command_uuid)
        logger.info("  password_ascii=%s", self.password_ascii)
        logger.info("  uart_ascii=%s", self.uart_ascii)
        logger.info("  reconnect_interval=%ss", self.reconnect_interval)

        # Estado BLE + control
        self.stop_evt = threading.Event()
        self.state = _ConnState()

        # Cola de líneas (ts_ms, line) y worker TX
        self._q: "queue.Queue[tuple[int, str]]" = queue.Queue(maxsize=20)
        self._tx_thread = threading.Thread(target=self._tx_worker, daemon=True, name=f"TX-{self.name}")
        self._tx_thread_started = False
        self._last_pub_ts = 0.0  # throttling de publicación

    # ---------- ciclo de vida ----------
    def stop(self) -> None:
        """Detiene el hilo y limpia recursos."""
        self.stop_evt.set()
        try:
            self._q.put_nowait((0, "__STOP__"))
        except queue.Full:
            pass
        if self._tx_thread_started:
            self._tx_thread.join(timeout=2)
        self._cleanup()

    def run(self) -> None:
        # arranca el worker de TX una sola vez
        if not self._tx_thread_started:
            self._tx_thread.start()
            self._tx_thread_started = True

        while not self.stop_evt.is_set():
            try:
                self._connect_to_ble()
                self._loop_notifications()
                break  # salió por stop

            except (BTLEDisconnectError, BTLEException) as e:
                logger.warning("[%s] desconectado: %s", self.device_name, e)
            except Exception as e:
                logger.exception("[%s] error inesperado: %s", self.device_name, e)

            # Reconectar tras limpiar
            self._cleanup()
            if self.stop_evt.is_set():
                break
            logger.info("[%s] reintentando en %ss ...", self.device_name, self.reconnect_interval)
            time.sleep(self.reconnect_interval)

        self._cleanup()

    # ---------- BLE ----------
    def _connect_to_ble(self) -> None:
        logger.info("[%s] connecting to %s ...", self.name, self.address)
        self.state.p = Peripheral(self.address, addrType="public")
        logger.info("[%s] connected", self.device_name)

        # Características
        self.state.tx_char = self.state.p.getCharacteristics(uuid=self.tx_uuid)[0]
        self.state.cmd_char = self.state.p.getCharacteristics(uuid=self.command_uuid)[0]

        logger.info("[%s] TX props=%s | CMD props=%s",
                    self.device_name,
                    self.state.tx_char.propertiesToString(),
                    self.state.cmd_char.propertiesToString())

        # Password (best-effort, CRLF y sin respuesta)
        if self.password_ascii:
            try:
                self.state.cmd_char.write((self.password_ascii + "\r\n").encode("ascii"), withResponse=False)
                time.sleep(0.1)
                logger.info("[%s] password enviada", self.device_name)
            except Exception as e:
                logger.info("[%s] WARN password write failed: %s (continuing)", self.name, e)

        # UART (best-effort, CRLF y sin respuesta)
        if self.uart_ascii:
            try:
                self.state.cmd_char.write((self.uart_ascii + "\r\n").encode("ascii"), withResponse=False)
                time.sleep(0.1)
                logger.info("[%s] UART configurada", self.device_name)
            except Exception as e:
                logger.info("[%s] WARN UART write failed: %s (continuing)", self.name, e)

        # Habilitar NOTIFY en TX: buscar CCCD (0x2902) y probar 0x0001/0x0003
        if "NOTIFY" not in self.state.tx_char.propertiesToString():
            raise RuntimeError(f"La característica TX {self.tx_uuid} no tiene NOTIFY")

        cccd_handle = self._find_cccd(self.state.tx_char)
        for value in (b"\x01\x00", b"\x03\x00"):
            try:
                self.state.p.writeCharacteristic(cccd_handle, value, withResponse=True)
                self.state.cccd_handle = cccd_handle
                logger.info("[%s] NOTIFY habilitado en tx_uuid=%s (cccd=%d, value=%s)",
                            self.device_name, self.tx_uuid, cccd_handle, value.hex())
                break
            except BTLEException as e:
                logger.warning("[%s] fallo al escribir CCCD=%d valor=%s: %s",
                               self.device_name, cccd_handle, value.hex(), e)

        logger.info("[%s] auth/UART attempted", self.name)
        self.state.p.setDelegate(_LineDelegate(self.device_name, self._enqueue_line))

    def _find_cccd(self, char) -> int:
        """Intenta localizar el descriptor 0x2902 (Client Characteristic Configuration)."""
        try:
            start = char.getHandle()
            # Escanea un rango corto alrededor para no levantar demasiados descriptores
            for d in self.state.p.getDescriptors(startHnd=start, endHnd=start + 12):
                if d.uuid.getCommonName() == "Client Characteristic Configuration":
                    return d.handle
        except Exception:
            pass
        # Fallback típico si el firmware no lista descriptores:
        return char.getHandle() + 1

    def _loop_notifications(self) -> None:
        """Espera notificaciones; si no hay, poll cada 1s para poder salir con stop_evt."""
        while not self.stop_evt.is_set():
            try:
                self.state.p.waitForNotifications(1.0)  # delegate -> _enqueue_line
            except (BTLEDisconnectError, BTLEException):
                raise
            except Exception as e:
                logger.info("[%s] notif err: %s", self.name, e)
                raise

    def _cleanup(self) -> None:
        try:
            if self.state.p:
                self.state.p.disconnect()
        except Exception:
            pass
        finally:
            self.state = _ConnState()

    # ---------- encolado rápido desde el callback ----------
    def _enqueue_line(self, line: str) -> None:
        ts = now_ms()
        try:
            self._q.put_nowait((ts, line))
        except queue.Full:
            # Si se llena, descartamos el más viejo para no bloquear
            try:
                _ = self._q.get_nowait()
                self._q.put_nowait((ts, line))
            except Exception:
                pass

    # ---------- worker que imprime/guarda ----------
    def _tx_worker(self) -> None:
        """
        Consume del queue y:
          - si parse == "json": intenta json + aplica field_map
          - si no: imprime RAW
        """
        while not self.stop_evt.is_set():
            try:
                ts_ms, line = self._q.get(timeout=1.0)
            except queue.Empty:
                continue
            if line == "__STOP__":
                break

            # Parseo
            if self.parse == "json":
                try:
                    obj = json.loads(line)              
                    if self.field_map and isinstance(obj, dict):
                        obj = {self.field_map.get(k, k): v for k, v in obj.items()}

                    logger.debug("[%s] %s JSON -> %s", self.device_name, self.sensor_id, obj)
                    self.mqtt_queue.put_nowait(
                        MQTTQueueItem(
                            sensor_id=self.sensor_id,
                            gas=obj["gas"],
                            temp=obj["temp"],
                            hum=obj["hum"],
                            pres=obj["pres"],
                            ts_ms=now_ms(),
                        )
                    )

                    self.db_queue.put_nowait(
                        SQLiteDatabaseItem(
                            sensor_id=self.sensor_id,
                            gas=obj["gas"],
                            temp=obj["temp"],
                            hum=obj["hum"],
                            pres=obj["pres"],
                            ts_ms=now_ms(),
                        )
                    )   
                except json.JSONDecodeError:
                    logger.error("[%s] %s RAW -> %s", self.device_name, self.sensor_id, line)
            else:
                logger.debug("[%s] %s RAW -> %s", self.device_name, self.sensor_id, line)

