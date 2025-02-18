.PHONY: test-snapshot-manager
test-snapshot-manager:
	# pytest --doctest-modules
	# Ensure previous data won't interfere with the new execution.
	coverage erase
	coverage run -m pytest
	coverage report -m
