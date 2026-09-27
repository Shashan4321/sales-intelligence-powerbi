.PHONY: all data etl customers expected test lint

all: data etl customers expected

data:        ## raw order-lines extract (seeded)
	PYTHONPATH=src python -m salesintel.generate

etl:         ## SQL: staging -> star schema -> quality checks -> data/gold/*.csv
	PYTHONPATH=src python -m salesintel.etl

customers:   ## cohorts, RFM, churn model + SHAP -> docs/img, reports/
	PYTHONPATH=src python -m salesintel.customers

expected:    ## expected values for validating the DAX measures
	PYTHONPATH=src python -m salesintel.expected

test:
	pytest -q

lint:
	ruff check . && ruff format --check . && sqlfluff lint sql/
