from dataclasses import dataclass

@dataclass
class MQTTQueueItem:
    """ Estructura para los datos MQTT con nueva estructura de topics """
    sensor_id: str
    sensor_type: str  # "amb" o "door" 
    sensor_numeric_id: str  # "a01", "a02", "d01", etc.
    temp: float
    hum: float
    pres: float
    ts_ms: int
    lux: float = None
    delta_g: float = None

@dataclass
class SQLiteDatabaseItem:
    """ Estructura para datos de base de datos """
    sensor_id: str
    temp: float
    hum: float
    pres: float
    ts_ms: int
    lux: float = None
    delta_g: float = None