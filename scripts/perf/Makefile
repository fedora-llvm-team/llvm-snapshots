YYYYMMDD?=$(shell date +%Y%m%d)
RESULTS_DIR?=$(PWD)/results

.PHONY: all
all: setup run

.PHONY: setup
setup:
	podman build -t evaluation .

.PHONY: run
run:
	mkdir -pv $(RESULTS_DIR)
	podman run -it --rm \
		-e YYYYMMDD=$(YYYYMMDD) \
		-e TMT_PLAN_DATA=/results \
		-v $(RESULTS_DIR):/results:Z \
		evaluation
