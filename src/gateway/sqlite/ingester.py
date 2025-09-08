import logging
import queue
import threading
from gateway.sqlite.db import SQLiteDatabase

logger = logging.getLogger(__name__)

class DBIngesterThread(threading.Thread):
    """
    Hilo base para ingerir datos en la base de datos SQLite
    """

    def __init__(self, db_queue: queue.Queue, database: SQLiteDatabase) -> None:
        super().__init__(daemon=True)
        self.stop_event = threading.Event()
        self.db_queue = db_queue
        self.db = database

    def run(self) -> None:
        """ Iniciar el hilo de ingesta a la base de datos SQLite"""
        while not self.stop_event.is_set():
            try:
                item = self.db_queue.get(timeout=1.0)
                if item:
                    logger.debug("ingestando item a la base de datos SQLite: %s", item)
                    self.db_queue.task_done()
            except queue.Empty:
                continue

    def stop(self) -> None:
        """ Detener el hilo de ingesta a la base de datos SQLite"""
        self.stop_event.set()
