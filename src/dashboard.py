import os
import time
import sqlite3
from datetime import datetime
from typing import Dict, Any, List

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

DB_PATH = "telemetry.db"
console = Console()


def fetch_dashboard_data() -> Dict[str, Any]:
    """Διαβάζει τα τελευταία δεδομένα από την SQLite χωρίς να κλειδώνει τη βάση."""
    if not os.path.exists(DB_PATH):
        return {"db_ready": False}

    try:
        with sqlite3.connect(DB_PATH, timeout=1.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 1. Συνολικά στατιστικά
            cursor.execute("SELECT COUNT(*) as total, SUM(buffered) as total_buffered FROM measurements")
            stats_row = cursor.fetchone()
            total_packets = stats_row["total"] if stats_row and stats_row["total"] else 0
            total_buffered = stats_row["total_buffered"] if stats_row and stats_row["total_buffered"] else 0

            # 2. Τελευταίες 2 μετρήσεις ανά κόμβο (για υπολογισμό ΔT/Δt)
            cursor.execute("""
                SELECT node_id, seq_num, timestamp, temp_c, voltage_v, lat, lon, buffered
                FROM measurements
                ORDER BY id DESC
                LIMIT 100
            """)
            recent_rows = [dict(r) for r in cursor.fetchall()]

            nodes_latest: Dict[str, List[Dict[str, Any]]] = {}
            for r in recent_rows:
                nid = r["node_id"]
                if nid not in nodes_latest:
                    nodes_latest[nid] = []
                if len(nodes_latest[nid]) < 2:
                    nodes_latest[nid].append(r)

            return {
                "db_ready": True,
                "total_packets": total_packets,
                "total_buffered": total_buffered,
                "active_nodes": len(nodes_latest),
                "nodes_latest": nodes_latest,
                "stream": recent_rows[:10]  # Τα 10 πιο πρόσφατα πακέτα
            }
    except sqlite3.OperationalError:
        return {"db_ready": False}


def build_header(data: Dict[str, Any]) -> Panel:
    """Φτιάχνει το πάνω μπάνερ με τα global μετρικά του συστήματος."""
    now_str = datetime.now().strftime("%H:%M:%S")
    if not data.get("db_ready"):
        return Panel(
            Text(f"⏳ Αναμονή για δημιουργία της βάσης '{DB_PATH}'... (Ξεκίνα τον server)", style="bold yellow"),
            title="[bold cyan]⚡ EdgePulse Live Telemetry Monitor[/bold cyan]",
            border_style="yellow"
        )

    total = data["total_packets"]
    buffered = data["total_buffered"]
    nodes = data["active_nodes"]
    recovery_pct = (buffered / total * 100.0) if total > 0 else 0.0

    summary = Text.assemble(
        (" 🟢 SYSTEM ONLINE ", "bold black on green"),
        (f"   📡 Ενεργοί Κόμβοι: ", "bold white"), (f"{nodes}   ", "bold cyan"),
        (f"📦 Σύνολο Πακέτων: ", "bold white"), (f"{total}   ", "bold green"),
        (f"🛡️ Διασωθέντα (Ring Buffer): ", "bold white"), (f"{buffered} ({recovery_pct:.1f}%)   ", "bold yellow"),
        (f"🕒 Ώρα: {now_str}", "dim white")
    )
    return Panel(summary, title="[bold cyan]⚡ EdgePulse — Real-Time Fleet & Cold-Chain Monitor[/bold cyan]", border_style="cyan")


def build_nodes_table(data: Dict[str, Any]) -> Panel:
    """Φτιάχνει τον πίνακα κατάστασης όλων των ενεργών κόμβων."""
    table = Table(box=box.SIMPLE_HEAVY, expand=True, header_style="bold cyan")
    table.add_column("Node ID", style="bold white")
    table.add_column("Seq #", justify="right")
    table.add_column("Temp (°C)", justify="right")
    table.add_column("Ρυθμός (ΔT/Δt)", justify="right")
    table.add_column("Τάση (V)", justify="right")
    table.add_column("GPS (Lat, Lon)", justify="center")
    table.add_column("Κατάσταση Κόμβου", justify="center")

    if not data.get("db_ready") or not data.get("nodes_latest"):
        table.add_row("-", "-", "-", "-", "-", "-", "[dim]Αναμονή πακέτων...[/dim]")
        return Panel(table, title="[bold white]📡 Κατάσταση Κόμβων (Edge Fleet)[/bold white]", border_style="blue")

    for node_id, history in data["nodes_latest"].items():
        latest = history[0]
        temp = latest["temp_c"]
        volt = latest["voltage_v"]

        # Υπολογισμός ΔT/Δt (°C/min) αν υπάρχει προηγούμενο πακέτο
        roc_str = "0.0 °C/m"
        roc_val = 0.0
        if len(history) > 1:
            prev = history[1]
            dt = latest["timestamp"] - prev["timestamp"]
            if dt > 0:
                roc_val = ((temp - prev["temp_c"]) / dt) * 60.0
                sign = "+" if roc_val >= 0 else ""
                roc_str = f"{sign}{roc_val:.1f} °C/m"

        # Χρωματισμός Θερμοκρασίας
        temp_style = "bold red" if temp > 8.0 else ("bold yellow" if temp > 5.0 else "bold green")
        roc_style = "bold red" if roc_val > 4.0 else "dim white"
        volt_style = "bold red" if volt < 11.5 else "bold green"

        # Καθορισμός Status Badge
        alerts = []
        if temp > 8.0:
            alerts.append("CRITICAL TEMP")
        if roc_val > 4.0:
            alerts.append("THERMAL SPIKE")
        if volt < 11.5:
            alerts.append("LOW VOLTAGE")

        if alerts:
            status_badge = f"[bold white on red] ⚠ {', '.join(alerts)} [/bold white on red]"
        elif latest["buffered"]:
            status_badge = "[bold black on cyan] 🔄 BATCH SYNCED [/bold black on cyan]"
        else:
            status_badge = "[bold green]● NOMINAL[/bold green]"

        table.add_row(
            node_id,
            f"#{latest['seq_num']}",
            f"[{temp_style}]{temp:.2f}°C[/{temp_style}]",
            f"[{roc_style}]{roc_str}[/{roc_style}]",
            f"[{volt_style}]{volt:.2f}V[/{volt_style}]",
            f"{latest['lat']:.4f}, {latest['lon']:.4f}",
            status_badge
        )

    return Panel(table, title="[bold white]📡 Κατάσταση Κόμβων (Edge Fleet)[/bold white]", border_style="blue")


def build_stream_table(data: Dict[str, Any]) -> Panel:
    """Φτιάχνει το κάτω panel με τη ζωντανή ροή των τελευταίων 10 πακέτων."""
    table = Table(box=box.MINIMAL_DOUBLE_HEAD, expand=True, header_style="bold magenta")
    table.add_column("Ώρα Μέτρησης", style="dim")
    table.add_column("Node ID", style="bold")
    table.add_column("Πακέτο", justify="right")
    table.add_column("Θερμοκρασία", justify="right")
    table.add_column("Τάση", justify="right")
    table.add_column("Πηγή Μετάδοσης", justify="center")

    if not data.get("db_ready") or not data.get("stream"):
        table.add_row("-", "-", "-", "-", "-", "[dim]Κενό ιστορικό[/dim]")
        return Panel(table, title="[bold white]📜 Ζωντανή Ροή Πακέτων (Τελευταία 10)[/bold white]", border_style="magenta")

    for pkt in data["stream"]:
        ts_str = datetime.fromtimestamp(pkt["timestamp"]).strftime("%H:%M:%S")
        is_buf = bool(pkt["buffered"])

        source_tag = (
            "[bold yellow]📦 OFFLINE RING BUFFER[/bold yellow]"
            if is_buf else "[bold green]⚡ LIVE STREAM[/bold green]"
        )

        t_color = "red" if pkt["temp_c"] > 8.0 else "green"
        v_color = "red" if pkt["voltage_v"] < 11.5 else "green"

        table.add_row(
            ts_str,
            pkt["node_id"],
            f"#{pkt['seq_num']}",
            f"[{t_color}]{pkt['temp_c']:.2f}°C[/{t_color}]",
            f"[{v_color}]{pkt['voltage_v']:.2f}V[/{v_color}]",
            source_tag
        )

    return Panel(table, title="[bold white]📜 Ζωντανή Ροή Πακέτων & Batch Sync Logs[/bold white]", border_style="magenta")


def generate_layout() -> Layout:
    """Συνθέτει το συνολικό Layout της οθόνης."""
    data = fetch_dashboard_data()

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="nodes", size=8),
        Layout(name="stream")
    )

    layout["header"].update(build_header(data))
    layout["nodes"].update(build_nodes_table(data))
    layout["stream"].update(build_stream_table(data))
    return layout


if __name__ == "__main__":
    console.clear()
    try:
        with Live(generate_layout(), refresh_per_second=2, screen=True) as live:
            while True:
                time.sleep(0.5)
                live.update(generate_layout())
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Το EdgePulse Dashboard τερματίστηκε.[/bold yellow]")