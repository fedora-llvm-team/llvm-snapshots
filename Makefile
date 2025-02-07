.PHONY: test-snapshot-manager
test-snapshot-manager:
	# pytest --doctest-modules
	coverage erase
	coverage run -m pytest
	coverage report -m
