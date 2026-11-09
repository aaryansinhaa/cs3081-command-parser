# CS3081 command parser. From a fresh clone:
#   cp .env.example .env
#   make up
#   make train
SHELL := /bin/bash
export PATH := $(HOME)/.local/bin:$(PATH)
CLUSTER := cc3081
PYTHON := $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; else echo python3; fi)
HOST_PORT ?= 8080

.PHONY: up down cluster build deploy train train-v2 label clean-data test lint evaluate load clean help

help:
	@echo "up down cluster build deploy label clean-data train train-v2 evaluate test lint load clean"

up:
	bash scripts/up.sh

down:
	k3d cluster delete $(CLUSTER)

cluster:
	bash scripts/create_cluster.sh

build:
	docker build -f service/Dockerfile -t cc3081/service:v1 .
	docker build -f worker/Dockerfile -t cc3081/worker:v1 .
	k3d image import cc3081/service:v1 cc3081/worker:v1 -c $(CLUSTER)

deploy:
	bash scripts/deploy.sh

label:
	kubectl delete job -n pipeline teacher-label --ignore-not-found
	kubectl apply -f kubernetes/pipeline/worker-job.yaml
	kubectl -n pipeline wait --for=condition=complete job/teacher-label --timeout=12h

clean-data:
	$(PYTHON) worker/clean.py --counts-out results/clean_counts.json

train:
	$(PYTHON) training/train.py --version v1 $(if $(SUBSET),--subset $(SUBSET),)

train-v2:
	$(PYTHON) training/train.py --version v2

evaluate:
	bash scripts/evaluate.sh

test:
	$(PYTHON) -m pytest -q

lint:
	.venv/bin/ruff check worker service training scripts tests

load:
	mkdir -p results
	$(PYTHON) -m locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m \
		--host http://localhost:$(HOST_PORT) --csv results/loadtest

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache
