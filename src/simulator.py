import time
import random
import httpx
from collections import deque
from rich.console import Console
from src.models import TelemetryPacket

console = Console()
SERVER_URL = "http://127.0.0.1:8000/api/v1/telemetry"

class EdgeNodeSimulator:
    def __init__(self, node_id: str, buffer_capacity: int = 100):
        self.node_id = node_id
        self.seq_num = 0
        self.ring_buffer = deque(maxlen=buffer_capacity)
        self.base_temp = 3.5
        self.voltage = 12.6

    def read_sensors(self, simulate_fault: bool = False) -> TelemetryPacket:
        self.seq_num += 1
        if simulate_fault:
            # Προσομοίωση βλάβης: απότομη άνοδος θερμοκρασίας + πτώση τάσης τροφοδοτικού
            self.base_temp += 0.8
            self.voltage = 11.1
        else:
            self.base_temp += random.uniform(-0.05, 0.05)
            self.voltage = 12.6 + random.uniform(-0.1, 0.1)

        return TelemetryPacket(
            node_id=self.node_id,
            seq_num=self.seq_num,
            timestamp=time.time(),
            temp_c=round(self.base_temp, 2),
            voltage_v=round(self.voltage, 2),
            lat=38.2466,
            lon=21.7346,
            buffered=False
        )

    def transmit(self, packet: TelemetryPacket, force_offline: bool = False):
        if force_offline:
            packet.buffered = True
            self.ring_buffer.append(packet)
            console.print(
                f"[bold yellow][OFFLINE - 4G LOST][/bold yellow] Πακέτο #{packet.seq_num} "
                f"αποθηκεύτηκε στο Ring Buffer (Μέγεθος: {len(self.ring_buffer)})"
            )
            return

        # Αν υπάρχουν πακέτα στο Ring Buffer, τα βάζουμε μπροστά για μαζική αποστολή (Batch Sync)
        payload_packets = list(self.ring_buffer) + [packet]

        try:
            with httpx.Client(timeout=2.0) as client:
                response = client.post(
                    SERVER_URL,
                    json={"packets": [p.model_dump() for p in payload_packets]}
                )
                data = response.json()

                if len(self.ring_buffer) > 0:
                    console.print(
                        f"[bold cyan][BATCH SYNC][/bold cyan] Εστάλησαν επιτυχώς "
                        f"{len(self.ring_buffer)} αποθηκευμένα πακέτα + το τρέχον #{packet.seq_num}!"
                    )
                    self.ring_buffer.clear()
                else:
                    console.print(
                        f"[bold green][ONLINE][/bold green] Πακέτο #{packet.seq_num} | "
                        f"Temp: {packet.temp_c}°C | Τάση: {packet.voltage_v}V"
                    )

                for anomaly in data.get("anomalies", []):
                    for msg in anomaly["alerts"]:
                        console.print(f"   [bold red]⚠ ALERT (Πακέτο #{anomaly['seq_num']}): {msg}[/bold red]")

        except httpx.RequestError:
            packet.buffered = True
            self.ring_buffer.append(packet)
            console.print(f"[bold yellow][SERVER UNREACHABLE][/bold yellow] Αποθήκευση #{packet.seq_num} στο Ring Buffer.")

if __name__ == "__main__":
    node = EdgeNodeSimulator(node_id="NODE-ACH-01")
    console.rule("[bold blue]EdgePulse Hardware Simulator Started[/bold blue]")

    for step in range(1, 13):
        is_offline_step = step in (4, 5, 6)   # Βήματα 4-6: Προσομοίωση απώλειας σήματος
        is_fault_step = step >= 9             # Βήματα 9+: Προσομοίωση βλάβης ψύξης/τάσης

        pkt = node.read_sensors(simulate_fault=is_fault_step)
        node.transmit(pkt, force_offline=is_offline_step)
        time.sleep(1.5)