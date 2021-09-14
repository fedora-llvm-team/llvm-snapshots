#!/usr/bin/env python3

from warnings import catch_warnings
from copr.v3 import Client, CoprRequestException
from copr.v3.proxies import build, package, project
import os
import sys
import datetime
import argparse


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

    def ensure_project(self, description: str, instructions: str):
        """
        Creates the copr project or ensures that it already exists.
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
                chroots=['fedora-rawhide-x86_64'],
                description=description,
                instructions=instructions.format(
                    self.ownername, self.projectname),
                enable_net=True,
                appstream=False)

    def make_packages(self, yyyymmdd: str, custom_script: str, packagenames: list[str]):
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
                    "script": custom_script.format(packagename, yyyymmdd),
                    "builddeps": "git make dnf-plugins-core fedora-packager tree curl sed",
                    "resultdir": "buildroot"
                }
            }
            if packagename in existingpackagenames:
                print("Resetting and editing package {} in {}/{}".format(packagename,
                      self.ownername, self.projectname))
                self.client.package_proxy.reset(
                    ownername=self.ownername, projectname=self.projectname, packagename=packagename)
                self.client.package_proxy.edit(**packageattrs)
            else:
                print("Creating package {} in {}/{}".format(packagename,
                      self.ownername, self.projectname))
                self.client.package_proxy.add(**packageattrs)

    def build_packages_chained(self, packagenames: list[str], chroots: list[str]):
        previous_build = None
        for packagename in packagenames:
            # See https://python-copr.readthedocs.io/en/latest/client_v3/build_options.html
            buildopts = {
                "timeout": 30*3600,
                "chroots": chroots
            }
            if previous_build != None:
                print("Creating chained-build for package {} in {}/{} after build-id {}".format(
                    packagename, self.ownername, self.projectname, previous_build.id), end='')
                buildopts['after_build_id'] = previous_build.id
            else:
                print("Creating build for package {} in {}/{}".format(packagename,
                      self.ownername, self.projectname), end='')

            try:
                self.client.package_proxy.build(
                    ownername=self.ownername,
                    projectname=self.projectname,
                    packagename=packagename,
                    buildopts=buildopts,
                )
            except CoprRequestException as ex:
                print("\nERROR: {}".format(ex))
                sys.exit(-1)
            print(" (build-id={}, state={})".format(previous_build.id,
                  previous_build.state))


def main():
    defaultpackagenames=["python-lit", "compat-llvm", "compat-clang", "llvm", "clang", "lld"]
    parser = argparse.ArgumentParser(description='Start LLVM snapshot builds on Fedora Copr.')
    parser.add_argument('--chroots',
                        dest='chroots',
                        metavar='CHROOT',
                        nargs='+',
                        default="fedora-rawhide-x86_64",
                        type=str,
                        help="list of chroots to build in (defaults to: fedora-rawhide-x86_64)")
    parser.add_argument('--packagenames',
                        dest='packagenames',
                        metavar='PACKAGENAME',
                        nargs='+',
                        default=defaultpackagenames,
                        type=str,
                        help="list of LLVM packagenames to build in order. Defaults to: {}".format(" ".join(defaultpackagenames)))
    parser.add_argument('--yyyymmdd',
                        dest='yyyymmdd',
                        default=datetime.date.today().strftime("%Y%m%d"),
                        type=str,
                        help="year month day combination to build for; defaults to today (e.g. 20210908)")
    parser.add_argument('--ownername',
                        dest='ownername',
                        default='kkleine',
                        type=str,
                        help="owner (or group) name of the copr project to be created or checked for existence (defaults to: kkleine)")
    parser.add_argument('--projectname',
                        dest='projectname',
                        default='llvm-snapshots',
                        type=str,
                        help="project name of the copr project (defaults to: llvm-snapshots)")
    parser.add_argument('--timeout',
                        dest='timeout',
                        default=30*3600,
                        type=int,
                        help="build timeout in seconds for each package (defaults to: 30*3600=108000)")
    args = parser.parse_args()

    builder = CoprBuilder(ownername=args.ownername, projectname=args.projectname)
    # For location see see https://stackoverflow.com/a/4060259
    location = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
    description = open(os.path.join(location, "project-description.md"), "r").read()
    instructions = open(os.path.join(location, "project-instructions.md"), "r").read()
    custom_script = open(os.path.join(location, "custom-script.sh.tpl"), "r").read()
    builder.ensure_project(description=description, instructions=instructions)
    builder.make_packages(yyyymmdd=args.yyyymmdd, custom_script=custom_script, packagenames=args.packagenames)
    builder.build_packages_chained(packagenames=args.packagenames, chroots=args.chroots)

if __name__ == "__main__":
    main()
