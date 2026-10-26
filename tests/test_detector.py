import time
from src.models import TelemetryPacket
from src.detector import AnomalyDetector

def test_rapid_temperature_rise_detection():
    detector = AnomalyDetector(max_roc_per_min=4.0)
    now = time.time()

    # Πρώτο πακέτο: Κανονική θερμοκρασία 3.0°C
    p1 = TelemetryPacket(node_id="TEST-01", seq_num=1, timestamp=now, temp_c=3.0, voltage_v=12.5, lat=0.0, lon=0.0)
    assert detector.analyze(p1) == []

    # Δεύτερο πακέτο: +1.5°C μέσα σε 5 δευτερόλεπτα (ισοδυναμεί με +18°C/λεπτό!)
    p2 = TelemetryPacket(node_id="TEST-01", seq_num=2, timestamp=now + 5.0, temp_c=4.5, voltage_v=12.5, lat=0.0, lon=0.0)
    alerts = detector.analyze(p2)
    assert any("THERMAL_SPIKE" in a for a in alerts)

def test_low_voltage_detection():
    detector = AnomalyDetector(min_voltage=11.5)
    p1 = TelemetryPacket(node_id="TEST-01", seq_num=1, timestamp=time.time(), temp_c=3.0, voltage_v=10.8, lat=0.0, lon=0.0)
    alerts = detector.analyze(p1)
    assert any("LOW_VOLTAGE" in a for a in alerts)