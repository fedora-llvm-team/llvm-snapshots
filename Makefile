.PHONY: build-diagrams
build-diagrams:
	$(eval temp_dir:=$(shell mktemp -d))
	$(eval yyyymmdd:=$(shell date '+%Y%m%d'))
	git show origin/gh-pages:build-stats-big-merge.csv > $(temp_dir)/build-stats-big-merge.csv
	git show origin/gh-pages:build-stats-pgo.csv > $(temp_dir)/build-stats-pgo.csv
	scripts/get-build-stats.py --copr-projectname "llvm-snapshots-big-merge-$(yyyymmdd)" | tee -a $(temp_dir)/build-stats-big-merge.csv
	scripts/get-build-stats.py --copr-projectname "llvm-snapshots-pgo-$(yyyymmdd)" | tee -a $(temp_dir)/build-stats-pgo.csv
	scripts/create-diagrams.py --datafile-big-merge $(temp_dir)/build-stats-big-merge.csv --datafile-pgo $(temp_dir)/build-stats-pgo.csv
	xdg-open index.html

.PHONY: test-snapshot-manager
test-snapshot-manager:
	# pytest --doctest-modules
	# Ensure previous data won't interfere with the new execution.
	coverage erase
	coverage run -m pytest
	coverage report -m
