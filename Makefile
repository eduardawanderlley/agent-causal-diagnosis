.PHONY: install test benchmark gate demo

install:
	pip install -e ".[dev]"

test:
	pytest -q

benchmark:
	python benchmarks/run_benchmark.py

gate:
	python scripts/regression_gate.py

demo:
	python -m support_agent "Can I still return PED-1004?" --fault prompt_drift
