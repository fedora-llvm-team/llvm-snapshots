# Container image that runs your code
FROM fedora:36

# Copies your code file from your action repository to the filesystem path `/` of the container
COPY create-spec-file.sh /create-spec-file.sh

# Code file to execute when the docker container starts up (`entrypoint.sh`)
ENTRYPOINT ["/create-spec-file.sh"]