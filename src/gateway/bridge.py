# bridge.py
from __future__ import annotations
import re
import json
import time
import threading
import queue
import logging
from typing import Optional, Tuple, Any, Deque, List
from collections import deque

import serial


# --------------------------------------------------------------------------------------
# Configura el logger desde tu app:
# logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
# --------------------------------------------------------------------------------------


class ArduinoBridge:
    """
    Puente serie con el sketch del Arduino (SIM7070G).
    Protocolo por líneas:
      <<<PING>>>     -> responde "PONG"
      <<<GPS?>>>     -> responde una línea JSON {lat,lon,acc_m,fix}
      <<<TOPIC>>>    -> (línea siguiente) topic
      <<<PAYLOAD>>>  -> (línea siguiente) payload
      <<<END>>>      -> publica y responde "OK" o "ERR"
      <<<AT>>>       -> (línea siguiente) comando AT; vuelca la respuesta

    Notas:
    - Escritura con CRLF.
    - DTR/RTS en False para evitar reset al abrir.
    - Lectura por líneas + expect() con timeouts cortos.
    - Gaps cortos por comando; wait_ok solo para END.
    """

    # ---- Tuning por defecto ----
    READY_WARMUP_S = 1.5     # tiempo tras abrir para “tragarse” banners iniciales
    WRITE_TIMEOUT_S = 2.0
    READ_TIMEOUT_S = 0.25    # timeout base de pyserial (no confundir con expect)
    GAP_FAST_S = 0.2         # gap entre pasos “ligeros”
    GAP_PUBLISH_S = 0.5      # gap entre pasos del publish
    AT_MIN_TIMEOUT_S = 5.0   # mínimo para respuestas AT
    END_WAIT_MIN_S = 20.0    # mínimo para esperar OK/ERR tras END

    def __init__(self,
                 port: str,
                 baud: int = 115200,
                 timeout: float = 0.1,
                 logger: Optional[logging.Logger] = None) -> None:
        self.port = port
        self.baud = baud
        self._timeout = float(timeout)
        self._ready_at: float = 0.0
        self._cmd_q: "queue.Queue[Tuple[str, Any, queue.Queue]]" = queue.Queue(maxsize=100)
        self._running = True
        self._worker = threading.Thread(target=self._serial_worker, daemon=True, name="SERIAL-BRIDGE")
        self._last_io_ts: float = 0.0
        self._log = logger or logging.getLogger("ArduinoBridge")
        self._ser: Optional[serial.Serial] = None

        self._open_serial()
        self._worker.start()

    # ---- context manager ----
    def __enter__(self) -> "ArduinoBridge":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ----------------------------------------------------------------------------------
    # Puerto serie
    # ----------------------------------------------------------------------------------
    def _open_serial(self) -> None:
        self._log.debug("Abriendo puerto %s @ %d", self.port, self.baud)
        ser = serial.Serial(
            port=self.port,
            baudrate=self.baud,
            timeout=1,
            write_timeout=self.WRITE_TIMEOUT_S,
            rtscts=False, dsrdtr=False, xonxoff=False,
        )
        try:
            # Evita reset en muchas placas
            ser.dtr = False
            ser.rts = False
        except Exception:
            pass

        time.sleep(0.15)
        try:
            ser.reset_input_buffer()
            ser.reset_output_buffer()
        except Exception:
            pass

        self._ser = ser
        # pequeño warm-up para que el sketch imprima READY/banner
        self._ready_at = time.time() + self.READY_WARMUP_S

    def _recover_serial(self) -> None:
        self._log.warning("Recuperando puerto serie…")
        try:
            if self._ser and self._ser.is_open:
                try:
                    self._ser.close()
                except Exception:
                    pass
            time.sleep(0.3)
            self._open_serial()
        except Exception as e:
            self._log.error("Falla al reabrir serial: %s", e)

    # ----------------------------------------------------------------------------------
    # Helpers I/O (solo worker)
    # ----------------------------------------------------------------------------------
    def _write_line(self, s: str) -> None:
        assert self._ser is not None
        data = (s + "\r\n").encode("utf-8", errors="ignore")
        self._log.debug("SER => %r", s)
        self._ser.write(data)
        self._ser.flush()

    def _readline_until(self, deadline: float) -> Optional[str]:
        """Lee una línea (\n) antes del deadline. Devuelve None si no hay línea completa."""
        assert self._ser is not None
        buf = bytearray()
        while time.time() < deadline:
            b = self._ser.read(1)
            if b:
                if b == b"\n":
                    line = buf.decode("utf-8", "ignore").rstrip("\r")
                    return line
                buf += b
            else:
                time.sleep(0.01)
        return None

    def _expect(self, patterns: List[str], timeout_s: float) -> Optional[str]:
        """Espera cualquier patrón (regex, case-insensitive) hasta timeout."""
        end = time.time() + max(0.05, timeout_s)
        rx = [re.compile(p, re.I) for p in patterns]
        while time.time() < end:
            line = self._readline_until(end)
            if line is None:
                continue
            self._log.debug("SER <= %r", line)
            for r in rx:
                if r.search(line):
                    return line
        return None

    def _drain_for(self, seconds: float) -> None:
        """Drena/lee por un ratito para tragarse banners."""
        end = time.time() + seconds
        while time.time() < end:
            line = self._readline_until(end)
            if not line:
                continue
            self._log.debug("DRN <= %r", line)

    # ----------------------------------------------------------------------------------
    # API pública (thread-safe, encolada)
    # ----------------------------------------------------------------------------------
    def ping(self, timeout: float = 2.0) -> bool:
        resp_q: "queue.Queue[bool]" = queue.Queue()
        try:
            self._cmd_q.put(("PING", None, resp_q), timeout=1.0)
            return resp_q.get(timeout=timeout)
        except Exception:
            return False

    def get_gps(self, timeout: float = 4.0) -> Optional[dict]:
        resp_q: "queue.Queue[Optional[dict]]" = queue.Queue()
        try:
            self._cmd_q.put(("GPS", None, resp_q), timeout=1.0)
            return resp_q.get(timeout=timeout)
        except Exception:
            return None

    def publish_lines(self, topic: str, payload: str, wait_ok: float = 30.0) -> bool:
        resp_q: "queue.Queue[bool]" = queue.Queue()
        try:
            self._cmd_q.put(("PUBLISH", (topic, payload, float(wait_ok)), resp_q), timeout=1.0)
            return resp_q.get(timeout=wait_ok + 5.0)
        except Exception:
            return False

    def send_at(self, cmd: str, read_timeout: float = 12.0) -> str:
        resp_q: "queue.Queue[str]" = queue.Queue()
        try:
            self._cmd_q.put(("AT", (cmd, float(read_timeout)), resp_q), timeout=1.0)
            return resp_q.get(timeout=read_timeout + 2.0)
        except Exception:
            return ""

    def send_direct_command(self, cmd: str, read_timeout: float = 10.0) -> str:
        resp_q: "queue.Queue[str]" = queue.Queue()
        try:
            self._cmd_q.put(("DIRECT", (cmd, float(read_timeout)), resp_q), timeout=1.0)
            return resp_q.get(timeout=read_timeout + 2.0)
        except Exception:
            return ""

    def send_health_command(self, timestamp: int, read_timeout: float = 10.0) -> str:
        """Envía el comando <<<HEALTH_TS>>> + timestamp para solicitar datos CPSI."""
        resp_q: "queue.Queue[str]" = queue.Queue()
        try:
            self._cmd_q.put(("HEALTH", (timestamp, float(read_timeout)), resp_q), timeout=1.0)
            return resp_q.get(timeout=read_timeout + 2.0)
        except Exception:
            return ""

    def close(self) -> None:
        try:
            if self._running:
                self._running = False
                dummy_q: "queue.Queue[None]" = queue.Queue()
                try:
                    self._cmd_q.put(("__STOP__", None, dummy_q), timeout=0.5)
                except Exception:
                    pass
                self._worker.join(timeout=3.0)
            try:
                if self._ser and self._ser.is_open:
                    self._ser.close()
            except Exception:
                pass
            self._log.info("Cerrado correctamente")
        except Exception as e:
            self._log.error("Error cerrando: %s", e)

    # ----------------------------------------------------------------------------------
    # Worker
    # ----------------------------------------------------------------------------------
    def _serial_worker(self) -> None:
        while self._running:
            try:
                cmd_type, data, response_queue = self._cmd_q.get(timeout=0.5)
            except queue.Empty:
                continue
            except Exception as e:
                self._log.error("Worker get error: %s", e)
                continue

            if cmd_type == "__STOP__":
                break

            # Warm-up inicial (tragarse banners READY, etc.)
            if time.time() < self._ready_at:
                time.sleep(max(0.0, self._ready_at - time.time()))
                # purga
                try:
                    self._drain_for(0.5)
                except Exception:
                    pass

            # Gap por comando
            now = time.time()
            gap = now - self._last_io_ts
            need_gap = self.GAP_PUBLISH_S if cmd_type == "PUBLISH" else self.GAP_FAST_S
            if gap < need_gap:
                time.sleep(need_gap - gap)

            # Ejecuta con un par de reintentos de puerto
            for attempt in range(2):
                try:
                    if cmd_type == "PING":
                        response_queue.put(self._do_ping()); break
                    elif cmd_type == "GPS":
                        response_queue.put(self._do_gps()); break
                    elif cmd_type == "PUBLISH":
                        topic, payload, wait_ok = data  # type: ignore[misc]
                        response_queue.put(self._do_publish_sync(str(topic), str(payload), float(wait_ok))); break
                    elif cmd_type == "AT":
                        at_cmd, rt = data  # type: ignore[misc]
                        response_queue.put(self._do_at(str(at_cmd), float(rt))); break
                    elif cmd_type == "DIRECT":
                        direct_cmd, rt = data  # type: ignore[misc]
                        response_queue.put(self._do_direct_command(str(direct_cmd), float(rt))); break
                    elif cmd_type == "HEALTH":
                        timestamp, rt = data  # type: ignore[misc]
                        response_queue.put(self._do_health_command(int(timestamp), float(rt))); break
                except Exception as e:
                    self._log.warning("Worker error (intent %d/2): %s", attempt + 1, e)
                    if attempt == 0:
                        self._recover_serial()
                        time.sleep(0.5)
                    else:
                        # fallo final → respuesta vacía/falsa
                        try:
                            if cmd_type == "PING":
                                response_queue.put(False)
                            elif cmd_type == "GPS":
                                response_queue.put(None)
                            elif cmd_type == "PUBLISH":
                                response_queue.put(False)
                            elif cmd_type in ("AT", "DIRECT", "HEALTH"):
                                response_queue.put("")
                        except Exception:
                            pass
                        break

            self._cmd_q.task_done()
            self._last_io_ts = time.time()

    # ----------------------------------------------------------------------------------
    # Implementaciones
    # ----------------------------------------------------------------------------------
    def _do_ping(self) -> bool:
        self._write_line("<<<PING>>>")
        line = self._expect([r"\bPONG\b"], timeout_s=2.0)
        ok = line is not None
        self._log.debug("PING %s", "OK" if ok else "FAIL")
        return ok

    def _do_gps(self) -> Optional[dict]:
        self._write_line("<<<GPS?>>>")
        # lee líneas hasta encontrar una JSON { ... }
        end = time.time() + 4.0
        text_chunks: Deque[str] = deque()
        while time.time() < end:
            line = self._readline_until(end)
            if not line:
                continue
            self._log.debug("SER <= %r", line)
            text_chunks.append(line)
            txt = "\n".join(text_chunks).strip()
            i0, i1 = txt.rfind("{"), txt.rfind("}")
            if i0 != -1 and i1 != -1 and i1 > i0:
                try:
                    return json.loads(txt[i0:i1 + 1])
                except Exception:
                    return None
        return None

    def _do_at(self, cmd: str, read_timeout: float) -> str:
        self._write_line("<<<AT>>>")
        # prompt laxo
        self._expect([r"\[send\]\s*comando AT", r"AT>", r".*"], timeout_s=1.2)
        self._write_line(cmd)
        # respuesta con mínimo razonable
        end = time.time() + max(self.AT_MIN_TIMEOUT_S, read_timeout)
        lines: List[str] = []
        last = time.time()
        while time.time() < end:
            line = self._readline_until(end)
            if line is None:
                # silencio breve: si ya hay líneas, corta tras 0.2s de calma
                if lines and (time.time() - last) > 0.2:
                    break
                continue
            self._log.debug("AT <= %r", line)
            lines.append(line)
            last = time.time()
        return "\n".join(lines)

    def _do_direct_command(self, cmd: str, read_timeout: float) -> str:
        self._write_line(cmd)
        end = time.time() + max(8.0, read_timeout)
        lines: List[str] = []
        last = time.time()
        while time.time() < end:
            line = self._readline_until(end)
            if line is None:
                if lines and (time.time() - last) > 0.2:
                    break
                continue
            self._log.debug("CMD <= %r", line)
            lines.append(line)
            last = time.time()
        return "\n".join(lines)

    def _do_health_command(self, timestamp: int, read_timeout: float) -> str:
        """Implementa el protocolo <<<HEALTH_TS>>> + timestamp."""
        self._write_line("<<<HEALTH_TS>>>")
        time.sleep(0.05)  # pequeño delay para que el Arduino procese
        self._write_line(str(timestamp))
        
        end = time.time() + max(8.0, read_timeout)
        lines: List[str] = []
        last = time.time()
        while time.time() < end:
            line = self._readline_until(end)
            if line is None:
                if lines and (time.time() - last) > 0.2:
                    break
                continue
            self._log.debug("HEALTH <= %r", line)
            lines.append(line)
            last = time.time()
        return "\n".join(lines)

    def _do_publish_sync(self, topic: str, payload: str, wait_ok: float) -> bool:
        import re

        # --- TOPIC ---
        self._write_line("<<<TOPIC>>>");  
        time.sleep(0.03)
        self._write_line(topic);          
        time.sleep(0.05)
        self._write_line("<<<PAYLOAD>>>")
        time.sleep(0.03)
        self._write_line(payload);        
        time.sleep(0.05)
        self._write_line("<<<END>>>")
     
        return True
