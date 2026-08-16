.PHONY: install quality test build example redteam clean

install:
	pip install -e .

quality:
	ruff check --no-cache src/doctoc tests
	ruff format --check src/doctoc tests
	mypy --strict src/doctoc

test:
	python3 -m pytest -q

build:
	rm -rf dist build *.egg-info
	python3 -m build

example:
	printf '# Demo\n\n## Alpha\n\n### Inner\n\n## Beta\n' > /tmp/doctoc_demo.md
	python3 -m doctoc generate /tmp/doctoc_demo.md
	python3 -m doctoc check /tmp/doctoc_demo.md
	rm -f /tmp/doctoc_demo.md

redteam:
	bash scripts/red_team.sh

clean:
	rm -rf dist build *.egg-info .pytest_cache .ruff_cache .mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
