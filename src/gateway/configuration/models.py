from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Dict, Optional
import yaml
from pathlib import Path

class CharSpec(BaseModel):
    uuid: str
    format: str = Field(description="int16_le|uint16_le|uint32_le|float32_le|bytes")
    scale: float = 1.0

class BleSpec(BaseModel):
    address: str
    interval_s: int = 15
    char_map: Dict[str, CharSpec]

class SensorCfg(BaseModel):
    sensor_id: str
    sensor_type: str = "env"
    ble: BleSpec

class GatewayCfg(BaseModel):
    id: str
    serial_port: str
    serial_baud: int = 115200

class BrokerCfg(BaseModel):
    topic_prefix: str = "fleet"

class DbCfg(BaseModel):
    path: str

# ---- BLUNO models ----
class BlunoDevice(BaseModel):
    name: str
    address: str
    sensor_id: str
    parse: str = "json"                 # "json" o "kv"
    field_map: Optional[Dict[str,str]] = None

class BlunoCfg(BaseModel):
    tx_uuid: str
    command_uuid: str
    password_ascii: Optional[str] = None   # se añade CRLF automáticamente
    uart_ascii: Optional[str] = None       # se añade CRLF automáticamente
    reconnect_interval: int = 5
    devices: list[BlunoDevice] = []

class Config(BaseModel):
    gateway: GatewayCfg
    broker: BrokerCfg
    db: DbCfg
    sensors: list[SensorCfg] = []
    bluno: Optional[BlunoCfg] = None

def load_config(path: str | Path) -> Config:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Config.model_validate(data)
