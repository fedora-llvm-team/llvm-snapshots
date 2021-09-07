#!/usr/bin/env python3

from copr.v3 import Client
from copr.v3.proxies import build, package, project
import os
from pprint import pprint


class CoprBuilder(object):
    """
    This class simplifies the creation of the copr project and packages as well
    as builds.
    """

    def __init__(self, ownername: str, projectname: str):
        """
        Creates a CoprBuilder object for the given owner/group and project name.

        If the environment contains COPR_URL, COPR_LOGIN, COPR_TOKEN, and
        COPR_USERNAME, we'll try to create a Copr client from those environment
        variables; otherwise, A Copr API client is created from the config file
        in ~/.config/copr. See https://copr.fedorainfracloud.org/api/ for how to
        create such a file.
        """
        if "COPR_URL" in os.environ and "COPR_LOGIN" in os.environ and "COPR_TOKEN" in os.environ and "COPR_USERNAME" in os.environ:
            config = {'copr_url': os.environ['COPR_URL'],
                      'login': os.environ['COPR_LOGIN'],
                      'token': os.environ['COPR_TOKEN'],
                      'username': os.environ['COPR_USERNAME']}
            self.client = Client(config)
            assert self.client.config == config
        else:
            self.client = Client.create_from_config_file()
        self.ownername = ownername
        self.projectname = projectname

        # This is the custom script that copr will execute in order to build a
        # package (see {} placeholder).
        self.script_template = """#!/bin/bash -xe
curl --compressed -s -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/kwk/llvm-daily-fedora-rpms/main/build.sh?$(uuidgen) | bash -s -- \\
    --verbose \\
    --reset-project \\
    --generate-spec-file \\
    --build-in-one-dir /workdir/buildroot \\
    --project {} \\
    --yyyymmdd "$(date +%Y%m%d)"
        """

    def make_project(self, description: str, instructions: str):
        """
        Create the copr project or ensures that it already exists.
        """
        existingprojects = self.client.project_proxy.get_list(self.ownername)
        existingprojectnames = [p.name for p in existingprojects]
        if self.projectname in existingprojectnames:
            print("Found project {}/{}".format(self.ownername, self.projectname))
            # We don't edit the project because we wouldn't know what chroots to build
            # in. Once the project is created then you can add chroots to it other than
            # rawhide and upon the next daily snapshot build, we will automatically
            # build for those chroots.
        else:
            print("Creating project {}/{}".format(self.ownername, self.projectname))
            self.client.project_proxy.add(
                ownername=self.ownername,
                projectname=self.projectname,
                chroots=["fedora-rawhide-x86_64"],
                description=description,
                instructions=instructions.format(
                    self.ownername, self.projectname),
                enable_net=True,
                appstream=False)

    def make_packages(self, packagenames: list[str]):
        """
        Creates or edits existing packages in the copr project. 
        """

        # Ensure all packages are either created or edited if they already exist
        packages = self.client.package_proxy.get_list(
            ownername=self.ownername, projectname=self.projectname)
        existingpackagenames = [p.name for p in packages]

        for packagename in packagenames:
            packageattrs = {
                "ownername": self.ownername,
                "projectname": self.projectname,
                "packagename": packagename,
                "source_type": "custom",
                # For source_dict see https://python-copr.readthedocs.io/en/latest/client_v3/package_source_types.html#custom
                "source_dict": {
                    "script": self.script_template.format(packagename),
                    "builddeps": "git make dnf-plugins-core fedora-packager tree curl sed",
                    "resultdir": "buildroot"
                }
            }
            if packagename in existingpackagenames:
                print("Resetting and editing package {} in {}/{}".format(packagename,
                      self.ownername, self.projectname))
                # pprint(self.client.build_proxy.get_list(ownername=self.ownername, projectname=self.projectname, packagename=packagename, status="running"))
                self.client.package_proxy.reset(
                    ownername=self.ownername, projectname=self.projectname, packagename=packagename)
                self.client.package_proxy.edit(**packageattrs)
            else:
                print("Creating package {} in {}/{}".format(packagename,
                      self.ownername, self.projectname))
                self.client.package_proxy.add(**packageattrs)

    def build_packages_chained(self, packagenames: list[str]):
        previous_build = None
        for packagename in packagenames:
            buildopts = {
                "timeout": 30*3600,
            }
            if previous_build != None:
                print("Creating chained-build for package {} in {}/{} after build-id {}".format(
                    packagename, self.ownername, self.projectname, previous_build.id), end='')
                buildopts['after_build_id'] = previous_build.id
            else:
                print("Creating build for package {} in {}/{}".format(packagename,
                      self.ownername, self.projectname), end='')
            previous_build = self.client.package_proxy.build(
                ownername=self.ownername,
                projectname=self.projectname,
                packagename=packagename,
                buildopts=buildopts,
            )
            print(" (build-id={}, state={})".format(previous_build.id,
                  previous_build.state))


def main():
    builder = CoprBuilder(ownername="kkleine", projectname="llvm-snapshots")

    description = """This project provides Fedora packages for daily snapshot builds of [LLVM](https://www.llvm.org) projects such as [clang](https://clang.llvm.org/), [lld](https://lld.llvm.org/) and many more.

The packages should at least be available for the `x86_64` Fedora rawhide version.

To get involved in this, please head over to: [https://github.com/kwk/llvm-daily-fedora-rpms](https://github.com/kwk/llvm-daily-fedora-rpms).
"""
    instructions = """
Please, use this at your own risk!

For instructions on how to use this repository, consult the [official docs](https://docs.pagure.org/copr.copr/how_to_enable_repo.html#how-to-enable-repo).

In theory, this should be enough on a recent Fedora version:

```
$ dnf copr enable {}/{}
```

Then install `clang` or some of the other packages. Please note, that we keep the packages available here for a week or so.
"""

    builder.make_project(description=description, instructions=instructions)
    packagenames = ["python-lit", "compat-llvm",
                    "compat-clang", "llvm", "clang", "lld"]
    builder.make_packages(packagenames=packagenames)
    builder.build_packages_chained(packagenames=packagenames)


if __name__ == "__main__":
    main()
