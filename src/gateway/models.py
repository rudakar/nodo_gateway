from dataclasses import dataclass

@dataclass
class MQTTQueueItem:
    """ """
    sensor_id: str
    gas: float
    temp: float
    hum: float
    pres: float
    ts_ms: int

@dataclass
class SQLiteDatabaseItem:
    """ """
    sensor_id: str
    gas: float
    temp: float
    hum: float
    pres: float
    ts_ms: int