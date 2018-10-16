.PHONY: all doc init test

all: check test doc

check:
	mypy --strict dim.py
	black --check --diff dim.py tests.py

test:
	pytest --doctest-modules --cov=dim dim.py tests.py
	coverage html

doc:
	PYTHONWARNINGS= make -C doc html

init:
	command -v pipenv >/dev/null || pip install pipenv
	pipenv install --dev
