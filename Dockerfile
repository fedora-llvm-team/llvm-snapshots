FROM fedora:34

RUN dnf install -y --setopt=tsflags=nodocs --setopt=install_weak_deps=False\
    dnf-plugins-core \
    fedora-packager \
    tree \
    && dnf clean all

# When later /etc/dnf/cache is mounted from the outside, this will help to speed
# up download.
RUN echo "keepcache=True" >> /etc/dnf/dnf.conf

RUN useradd --create-home johndoe

# We still need to install packages using "dnf builddep my.spec" so we need to
# be able to execute commands using sudo.
RUN usermod -aG wheel johndoe
# Allows people in group wheel to run all commands (without a password)
RUN echo "johndoe ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers

USER johndoe
ENV PATH="/home/johndoe/bin:${PATH}" HOME=/home/johndoe
RUN echo '%_topdir /home/johndoe/rpmbuild' > /home/johndoe/.rpmmacros
RUN DEBUG=1 rpmdev-setuptree

WORKDIR /home/johndoe/rpmbuild
COPY --chown=johndoe:johndoe home/johndoe/bin /home/johndoe/bin
RUN chown -Rfv johndoe:johndoe /home/johndoe


ENTRYPOINT [ "/home/johndoe/bin/build.sh" ]