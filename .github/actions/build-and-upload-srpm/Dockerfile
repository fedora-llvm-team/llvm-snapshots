# Container image that runs your code
FROM fedora:36

RUN dnf install -y --setopt=tsflags=nodocs --setopt=install_weak_deps=False \
    curl \
    git \
    copr-cli \
    rpmdevtools \
    rpm-build \
   && dnf clean all

# Copies your code file from your action repository to the filesystem path `/` of the container
COPY build-and-upload-srpm.sh /build-and-upload-srpm.sh

# Code file to execute when the docker container starts up (`entrypoint.sh`)
ENTRYPOINT ["/build-and-upload-srpm.sh"]
