all:
	docker build -t foo .
	docker run \
		-it \
		--rm \
		foo \
			--project compiler-rt \
			--build-srpm