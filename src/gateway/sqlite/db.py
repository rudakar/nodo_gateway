""" Módulo de base de datos SQLite """
from __future__ import annotations
import json
import logging
import time
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts_ms     INTEGER NOT NULL,
  device    TEXT,
  sensor_id TEXT,
  payload   TEXT
);
"""

def now_ms() -> int:
    """Devuelve timestamp actual en ms."""
    return int(time.time() * 1000)

class SQLiteDatabase():
    """Clase para manejar la base de datos SQLite."""
    def __init__(self, path: str) -> None:
        logging.info("estableciendo conexión sqlite en %s", path)
        self.connection: Optional[sqlite3.Connection] = None

    def connect(self, path: str) -> None:
        """ Conecta a la base de datos SQLite y crea tablas si no existen. """
        self.connection = sqlite3.connect(path, timeout=2)
        cur = self.connection.cursor()
        if cur is not None:
            cur.executescript(SCHEMA)
            self.connection.commit()

        cur.close()
        logging.warning("conexión sqlite establecida")

    def close(self) -> None:
        """ Cierra la conexión a la base de datos SQLite. """
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.warning("conexión sqlite cerrada")


    def store_reading(
        self,
        device: str,
        sensor_id: str,
        payload: dict | str,
    ) -> None:
        """Guarda una lectura de datos."""

        if self.connection is None:
            logger.error("no hay conexión sqlite, ignorando escritura de lectura")
            return
        if not isinstance(payload, str):
            payload = json.dumps(payload, ensure_ascii=False)

        cur = self.connection.cursor()
        cur.execute(
            "INSERT INTO readings (ts_ms, device, sensor_id, payload) VALUES (?, ?, ?, ?)",
            (now_ms(), device, sensor_id, payload),
        )
        self.connection.commit()
