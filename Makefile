PYTHON = python3

all:
	uv run --with-requirements requirements.txt python grademe.py

lint:
	@$(PYTHON) -m flake8 src
	@$(PYTHON) -m mypy src --warn-return-any --warn-unused-ignores \
		--ignore-missing-imports --disallow-untyped-defs \
		--check-untyped-defs
debug:
	@$(PYTHON) -m pdb -m src

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -fr .grademe_session rendu
	rm -fr .mypy_cache
	rm -fr .venv
