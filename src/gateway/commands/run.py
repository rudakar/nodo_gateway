""" Módulo para ejecutar el gateway. """
import logging
import signal
from queue import Queue
from typing import List, Sequence

from gateway.bluno.bluno import BlunoWorker
from gateway.bridge import ArduinoBridge
from gateway.configuration.config_loader import BlunoDevice, Configuration, load_config
from gateway.health.health_thread import HealthThread
from gateway.models import MQTTQueueItem, SQLiteDatabaseItem
from gateway.mqtt.publisher import MQTTThread
from gateway.sqlite.db import SQLiteDatabase
from gateway.sqlite.ingester import DBIngesterThread


logger = logging.getLogger(__name__)

def handle_exit_signal(
    bluno_threads: List[BlunoWorker],
    mqtt_connection: MQTTThread,
    health_thread: HealthThread,
    db: SQLiteDatabase,
):
    """Maneja la señal de salida para cerrar hilos y conexiones de forma ordenada."""
    try:
        if mqtt_connection and mqtt_connection.is_alive():
            mqtt_connection.stop()
            logger.info("hilo publisher detenido")

        if health_thread and health_thread.is_alive():
            health_thread.stop()
            logger.info("hilo health detenido")

        if bluno_threads:
            for worker in bluno_threads:
                if worker.is_alive():
                    worker.stop()
                    logger.info("hilo bluno detenido")
            for worker in bluno_threads:
                if worker.is_alive():
                    worker.join(timeout=2.0)
                    logger.info("hilo bluno joined")
        if db:
            db.close()
    except RuntimeError:
        logger.warning("error al manejar la señal de salida")



def run():
    """Función principal que arranca el gateway."""
    cfg = load_config("config.yaml")
    logger.info("configuración cargada")
    db_ingester_queue: Queue[MQTTQueueItem] = Queue()
    mqtt_publisher_queue: Queue[MQTTQueueItem] = Queue()
    db = initialize_database(cfg.db.path)
    bridge = ArduinoBridge(cfg.gateway.serial_port, cfg.gateway.serial_baud)

    mqtt_publisher_thread = MQTTThread(mqtt_publisher_queue, bridge, gateway_id=cfg.gateway.id)
    mqtt_publisher_thread.start()


    db_ingester_thread = DBIngesterThread(db_ingester_queue, db)
    db_ingester_thread.start()

    logger.info("4g ats bridge arrancado")
    logger.info("arrancando hilos bluno...")
    bluno_threads: Sequence[BlunoWorker] = list(initialize_bluno_workers(cfg, mqtt_publisher_queue, db_ingester_queue))
    for worker in bluno_threads:
        worker.start()

    health_publisher = HealthThread(bridge, interval=30)
    health_publisher.start()
    logger.info("health thread arrancado")

    signal.pause()
    logger.warning("señal de salida recibida, cerrando hilos...")
    handle_exit_signal(
        bluno_threads = bluno_threads,
        mqtt_connection=mqtt_publisher_thread,
        health_thread=health_publisher,
        db=db
    )


def initialize_database(path: str) -> SQLiteDatabase:
    """Inicializa la base de datos SQLite creando las tablas necesarias."""
    sqlite_database = SQLiteDatabase(path)
    sqlite_database.connect(path)
    return sqlite_database

def initialize_bluno_workers(
        cfg: Configuration , 
        mqtt_queue: Queue[MQTTQueueItem], 
        db_queue: Queue[SQLiteDatabaseItem]
    ) -> List[BlunoWorker]:
    """Inicializa y arranca los hilos BlunoWorker según la configuración."""
    workers = []
    for device_cfg in cfg.bluno.devices:
        device = BlunoDevice(
            name = device_cfg.name,
            address = device_cfg.address,
            sensor_id = device_cfg.sensor_id,
            sensor_type = device_cfg.sensor_type,
            sensor_numeric_id = device_cfg.sensor_numeric_id,
            tx_uuid = device_cfg.tx_uuid,
            command_uuid = device_cfg.command_uuid,
            password_ascii = device_cfg.password_ascii,
            uart_ascii = device_cfg.uart_ascii,
            reconnect_interval = device_cfg.reconnect_interval,
            parse = device_cfg.parse,
            field_map = device_cfg.field_map,
        )
        worker = BlunoWorker(device, mqtt_queue, db_queue)
        workers.append(worker)
    return workers
