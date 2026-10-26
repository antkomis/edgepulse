PYTHON = ./venv/bin/python
PIP = ./venv/bin/pip
PYTEST = ./venv/bin/pytest
UVICORN = ./venv/bin/uvicorn

.PHONY: help install test server dashboard sim demo clean

help:
	@echo "⚡ EdgePulse — Διαθέσιμες Εντολές:"
	@echo "  make install    -> Δημιουργεί το venv και εγκαθιστά τις βιβλιοθήκες"
	@echo "  make test       -> Τρέχει τα Unit Tests (pytest)"
	@echo "  make server     -> Ξεκινάει τον FastAPI Server"
	@echo "  make dashboard  -> Ανοίγει το Live Terminal Dashboard"
	@echo "  make sim        -> Ξεκινάει τον Hardware Simulator"
	@echo "  make demo       -> Καθαρίζει τη βάση, σηκώνει Server στο background & τρέχει τον Simulator"
	@echo "  make clean      -> Διαγράφει προσωρινά αρχεία και την τοπική βάση telemetry.db"

install:
	python3 -m venv venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

test:
	$(PYTEST) -v

server:
	$(UVICORN) src.server:app --host 127.0.0.1 --port 8000

dashboard:
	$(PYTHON) -m src.dashboard

sim:
	$(PYTHON) -m src.simulator

demo:
	@rm -f telemetry.db
	@echo "🚀 Εκκίνηση FastAPI Server στο παρασκήνιο..."
	@$(UVICORN) src.server:app --host 127.0.0.1 --port 8000 --log-level error & \
	SERVER_PID=$$!; \
	trap "kill $$SERVER_PID 2>/dev/null" EXIT; \
	sleep 1.5; \
	$(PYTHON) -m src.simulator

clean:
	rm -rf __pycache__ src/__pycache__ tests/__pycache__ .pytest_cache telemetry.db