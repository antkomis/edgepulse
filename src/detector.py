from collections import deque
from typing import Dict, List, Tuple
from src.models import TelemetryPacket

class AnomalyDetector:
    def __init__(self, window_size: int = 10, max_roc_per_min: float = 4.0, min_voltage: float = 11.5):
        self.window_size = window_size
        self.max_roc_per_min = max_roc_per_min  # Μέγιστος επιτρεπτός ρυθμός ανόδου (°C/λεπτό)
        self.min_voltage = min_voltage          # Όριο χαμηλής τάσης τροφοδοτικού/μπαταρίας
        self.history: Dict[str, deque] = {}

    def analyze(self, packet: TelemetryPacket) -> List[str]:
        alerts: List[str] = []
        node_history = self.history.setdefault(packet.node_id, deque(maxlen=self.window_size))

        # 1. Έλεγχος Πτώσης Τάσης (Hardware / Power Supply Fault)
        if packet.voltage_v < self.min_voltage:
            alerts.append(f"LOW_VOLTAGE: {packet.voltage_v:.2f}V (Κίνδυνος απώλειας τροφοδοσίας)")

        # 2. Έλεγχος Ρυθμού Μεταβολής Θερμοκρασίας (ΔT / Δt)
        if len(node_history) >= 1:
            prev_time, prev_temp = node_history[-1]
            dt_seconds = packet.timestamp - prev_time

            if dt_seconds > 0:
                d_temp = packet.temp_c - prev_temp
                roc_per_min = (d_temp / dt_seconds) * 60.0

                if roc_per_min > self.max_roc_per_min:
                    alerts.append(
                        f"THERMAL_SPIKE: Άνοδος +{roc_per_min:.1f}°C/min (Πιθανή ανοιχτή πόρτα ή βλάβη ψύξης)"
                    )

        # 3. Έλεγχος Απόλυτου Ορίου Ασφαλείας
        if packet.temp_c > 8.0:
            alerts.append(f"CRITICAL_TEMP: {packet.temp_c:.1f}°C (Υπέρβαση ορίου ασφαλείας)")

        node_history.append((packet.timestamp, packet.temp_c))
        return alerts