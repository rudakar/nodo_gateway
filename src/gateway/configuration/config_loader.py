# src/gateway/settings.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

@dataclass
class Arduino4GConfiguration:
    """ Configuaración del puerto serie 4G sobre el arduino"""
    id: str = "1"
    serial_port: str = "/dev/ttyACM0"
    serial_baud: int = 115200


@dataclass
class BrokerConfiguration:
    topic_prefix: str = "fleet"


@dataclass
class SQLiteDBConfiguration:
    path: str = "./data/gateway.db"


@dataclass
class BlunoDevice:
    name: str
    address: str
    sensor_id: str
    sensor_type: str
    sensor_numeric_id: str
    tx_uuid: str
    command_uuid: str 
    password_ascii: str 
    uart_ascii: str 
    reconnect_interval: int
    parse: str = "json"                     # "json" o "kv"
    field_map: Optional[Dict[str, str]] = None


@dataclass
class BlunoConfiguration:
    tx_uuid: str
    command_uuid: str
    password_ascii: str
    uart_ascii: str
    reconnect_interval: int = 5
    devices: List[BlunoDevice] = field(default_factory=list)


@dataclass
class Configuration:
    gateway: Arduino4GConfiguration
    broker: BrokerConfiguration
    db: SQLiteDBConfiguration
    truck_id: str = "truck-01"
    sensors: List[Dict[str, Any]] = field(default_factory=list)
    bluno: Optional[BlunoConfiguration] = None


def _ensure_str(d: Dict[str, Any], key: str, default: str) -> str:
    v = d.get(key, default)
    if not isinstance(v, str):
        v = str(v)
    return v


def load_config(path: str = "config.yaml") -> Configuration:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config no encontrado: {p.resolve()}")

    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    gw = data.get("gateway", {})
    broker = data.get("broker", {})
    db = data.get("db", {})
    bl = data.get("bluno", None)

    gateway = Arduino4GConfiguration(
        id=_ensure_str(gw, "id", "1"),
        serial_port=_ensure_str(gw, "serial_port", "/dev/ttyACM0"),
        serial_baud=int(gw.get("serial_baud", 115200)),
    )

    broker_cfg = BrokerConfiguration(
        topic_prefix=_ensure_str(broker, "topic_prefix", "fleet")
    )

    db_cfg = SQLiteDBConfiguration(
        path=_ensure_str(db, "path", "./data/gateway.db")
    )

    sensors = data.get("sensors", []) or []

    bluno_cfg: Optional[BlunoConfiguration] = None
    if bl:
        devs_cfg = []
        for d in bl.get("devices", []) or []:
            devs_cfg.append(
                BlunoDevice(
                    name=_ensure_str(d, "name", "Bluno"),
                    address=_ensure_str(d, "address", ""),
                    sensor_id=_ensure_str(d, "sensor_id", "sensor"),
                    sensor_type=_ensure_str(d, "sensor_type", "amb"),
                    sensor_numeric_id=_ensure_str(d, "sensor_numeric_id", "a01"),
                    parse=_ensure_str(d, "parse", "json"),
                    field_map=d.get("field_map"),
                    tx_uuid=_ensure_str(d, "tx_uuid", "0000dfb1-0000-1000-8000-00805f9b34fb"),
                    command_uuid=_ensure_str(d, "command_uuid", "0000dfb2-0000-1000-8000-00805f9b34fb"),
                    password_ascii=_ensure_str(d, "password_ascii", "AT+PASSWORD=DFRobot"),
                    uart_ascii=_ensure_str(d, "uart_ascii", "AT+CURRUART=115200"),
                    reconnect_interval=int(d.get("reconnect_interval", 5)),
                )
            )
        bluno_cfg = BlunoConfiguration(
            tx_uuid=_ensure_str(bl, "tx_uuid", "0000dfb1-0000-1000-8000-00805f9b34fb"),
            command_uuid=_ensure_str(bl, "command_uuid", "0000dfb2-0000-1000-8000-00805f9b34fb"),
            password_ascii=_ensure_str(bl, "password_ascii", "AT+PASSWORD=DFRobot"),
            uart_ascii=_ensure_str(bl, "uart_ascii", "AT+CURRUART=115200"),
            reconnect_interval=int(bl.get("reconnect_interval", 5)),
            devices=devs_cfg,
        )

    return Configuration(
        truck_id=_ensure_str(gw, "id", "truck-01"),
        gateway=gateway,
        broker=broker_cfg,
        db=db_cfg,
        sensors=sensors,
        bluno=bluno_cfg,
    )
