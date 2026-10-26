import sqlite3
from fastapi import FastAPI
from src.models import TelemetryBatch
from src.detector import AnomalyDetector

app = FastAPI(title="EdgePulse Telemetry Server", version="1.0.0")
detector = AnomalyDetector()

def init_db():
    with sqlite3.connect("telemetry.db") as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id TEXT,
                seq_num INTEGER,
                timestamp REAL,
                temp_c REAL,
                voltage_v REAL,
                lat REAL,
                lon REAL,
                buffered INTEGER
            )
        """)

init_db()

@app.post("/api/v1/telemetry")
async def ingest_telemetry(batch: TelemetryBatch):
    all_alerts = []
    with sqlite3.connect("telemetry.db") as conn:
        for pkt in batch.packets:
            conn.execute(
                "INSERT INTO measurements (node_id, seq_num, timestamp, temp_c, voltage_v, lat, lon, buffered) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (pkt.node_id, pkt.seq_num, pkt.timestamp, pkt.temp_c, pkt.voltage_v, pkt.lat, pkt.lon, int(pkt.buffered))
            )
            alerts = detector.analyze(pkt)
            if alerts:
                all_alerts.append({"seq_num": pkt.seq_num, "alerts": alerts})

    return {
        "status": "ok",
        " ingested_count": len(batch.packets),
        "anomalies": all_alerts
    }