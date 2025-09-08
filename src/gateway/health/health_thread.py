import threading
import time
from gateway.bridge import ArduinoBridge


class HealthThread(threading.Thread):
    """
    Hilo que publica un latido periódico vía ArduinoBridge (modo por líneas).
    No usa atributo ._stop (para no romper threading tras fork).
    """

    def __init__(self, bridge: ArduinoBridge, interval: int = 120):
        super().__init__(daemon=True)
        self.bridge = bridge
        self.interval = interval
        self.running = True

    def run(self):
        # Esperar un tiempo considerable al inicio para que todos los sistemas se estabilicen
        # Incluyendo la conexión de los sensores BLE y el bridge del Arduino
        time.sleep(30)
        
        while self.running:
            try:
                # Usar el nuevo protocolo <<<HEALTH_TS>>> + timestamp
                timestamp = int(time.time() * 1000)  # timestamp en milisegundos
                
                # Enviar comando health y recibir respuesta con datos CPSI
                health_response = self.bridge.send_health_command(timestamp, read_timeout=10.0)
                
                if health_response.strip():
                    print(f"Health command response: {health_response}")
                    print(f"Health message with CPSI data sent successfully at timestamp {timestamp}")
                else:
                    print(f"Error: No response from health command at timestamp {timestamp}")
                
                # Esperar el intervalo o hasta que se detenga
                for _ in range(self.interval):
                    if not self.running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                print(f"Error en health thread: {e}")
                time.sleep(5)  # Esperar un poco antes de reintentar

    def stop(self):
        self.running = False
        