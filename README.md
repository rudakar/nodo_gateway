# iot-gateway

Raspberry Pi que:
- Lee sensores **BLE** (por UUID/escala/formato)
- Guarda en **SQLite**
- Publica a **MQTT** a través de un Arduino con **SIM7070G** (Cat-M1/NB-IoT)

## Requisitos
- Python 3.11
- Poetry (`pipx install poetry`)

## Instalar
```bash
poetry install
