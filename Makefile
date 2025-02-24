.PHONY: test-snapshot-manager
test-snapshot-manager: ci-coverage

# CI recipes

.PHONY: ci-coverage
ci-coverage:
	# Ensure previous data won't interfere with the new execution.
	coverage erase
	coverage run -m pytest
	coverage report -m

.PHONY: ci-test
ci-test:
	pytest
