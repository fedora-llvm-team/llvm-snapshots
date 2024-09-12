.PHONY: all
all: setup run

.PHONY: setup
setup:
	podman build -t evaluation .

.PHONY: run
run:
	podman run -it --rm evaluation
