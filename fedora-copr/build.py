#!/usr/bin/env python3

import datetime
import argparse
import os
from copr.v3 import Client, CoprRequestException
import os
import sys

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

        :param str ownername: copr user/group name to use throughout the build process
        :param str projectname: copr project name to use throught the build process
        """
        if "COPR_URL" in os.environ and "COPR_LOGIN" in os.environ and "COPR_TOKEN" in os.environ and "COPR_USERNAME" in os.environ:
            config = {'copr_url': os.environ['COPR_URL'],
                      'login': os.environ['COPR_LOGIN'],
                      'token': os.environ['COPR_TOKEN'],
                      'username': os.environ['COPR_USERNAME']}
            self.__client = Client(config)
            assert self.__client.config == config
        else:
            self.__client = Client.create_from_config_file()
        self.__ownername = ownername
        self.__projectname = projectname

    def make_or_edit_project(self, description: str, instructions: str, chroots: list[str], delete_project: bool=False) -> None:
        """
        Creates the copr project or ensures that it already exists and edits it.

        :param str description: a descriptive text of the project to create or edit
        :param str instrucitons: a text for the instructions of how to enable this project
        """
        if delete_project == True:
            # TODO: implement me
            sys.exit(-1)
                
        existingprojects = self.__client.project_proxy.get_list(self.__ownername)
        existingprojectnames = [p.name for p in existingprojects]
        if self.__projectname in existingprojectnames:
            print("Found project {}/{}".format(self.__ownername, self.__projectname))
            # We don't edit the project because we wouldn't know what chroots to build
            # in. Once the project is created then you can add chroots to it other than
            # rawhide and upon the next daily snapshot build, we will automatically
            # build for those chroots.
        else:
            print("Creating project {}/{}".format(self.__ownername, self.__projectname))
            # NOTE: devel_mode=True means that one has to manually create the repo.
            self.__client.project_proxy.add(
                ownername=self.__ownername,
                projectname=self.__projectname,
                chroots=chroots,
                description=description,
                instructions=instructions.format(
                    self.__ownername, self.__projectname),
                enable_net=True,
                devel_mode=True,
                appstream=False)

    def make_packages(self, yyyymmdd: str, custom_script: str, packagenames: list[str]) -> None:
        """
        Creates or edits existing packages in the copr project.

        :param str yyyymmdd: the date in backwards order for which to create the package
            this refers to the date for which the source snapshot will be taken.
        :param str custom_script: the script to execute when the package is built
        :param list[str] packagenames: these packages will be created
        """

        # Ensure all packages are either created or edited if they already exist
        packages = self.__client.package_proxy.get_list(
            ownername=self.__ownername, projectname=self.__projectname)
        existingpackagenames = [p.name for p in packages]

        for packagename in packagenames:
            packageattrs = {
                "ownername": self.__ownername,
                "projectname": self.__projectname,
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
                      self.__ownername, self.__projectname))
                self.__client.package_proxy.reset(
                    ownername=self.__ownername, projectname=self.__projectname, packagename=packagename)
                self.__client.package_proxy.edit(**packageattrs)
            else:
                print("Creating package {} in {}/{}".format(packagename,
                      self.__ownername, self.__projectname))
                self.__client.package_proxy.add(**packageattrs)

    def build_packages_chained(self, packagenames: list[str], chroots: list[str]) -> None:
        """
        Builds the list of packages for the given chroots in the order they are given.
        
        NOTE: We kick-off builds for each chroot individually so that an x86_64 build
        doesn't have to wait for a potentially slower s390x build.

        :param list[str] packagenames: the packages to be built
        :param list[str] chroots: the chroots for which the packages will be built
        """
        for chroot in chroots:
            previous_build_id = None
            for packagename in packagenames:
                build= self.__build_package(packagename, [chroot], build_after_id=previous_build_id)
                previous_build_id = build.id
                print(" (build-id={}, state={})".format(previous_build_id, build.state))

    def __build_package(self, package_name: str, chroots: list[str], build_after_id: int=None):
        build = None
        try:
            print("Creating build for package {} in {}/{}".format(package_name,
                    self.__ownername, self.__projectname), end='')
            build = self.__client.package_proxy.build(
                ownername=self.__ownername,
                projectname=self.__projectname,
                packagename=package_name,
                # See https://python-copr.readthedocs.io/en/latest/client_v3/build_options.html
                buildopts={
                    "timeout": 30*3600,
                    "chroots": chroots,
                    "after_build_id": build_after_id
                },
            )
        except CoprRequestException as ex:
            print("\nERROR: {}".format(ex))
            sys.exit(-1)
        print(" (build-id={}, state={})".format(build.id, build.state))
        return build

    def build_all(self, chroots: list[str], with_compat:bool=False) -> None:
        """
        Builds everyting for the given chroots and creates optimal Copr batches.
        
        NOTE: We kick-off builds for each chroot individually so that an x86_64 build
        doesn't have to wait for a potentially slower s390x build.
        """
        for chroot in chroots:
            python_lit_build = self.__build_package("python-lit", [chroot])
            llvm_compat_build = None
            clang_compat_build = None
            if with_compat == True:
                llvm_compat_build = self.__build_package("compat-llvm", [chroot], build_after_id=python_lit_build.id)
                clang_compat_build = self.__build_package("compat-clang", [chroot], build_after_id=llvm_compat_build.id)
            llvm_build = self.__build_package("llvm", [chroot], build_after_id=llvm_compat_build.id if with_compat else python_lit_build.id)
            lld_build = self.__build_package("lld", [chroot], build_after_id=llvm_build.id)
            clang_build = self.__build_package("clang", [chroot], build_after_id=clang_compat_build.id if with_compat else llvm_build.id)
            compiler_rt_build = self.__build_package("compiler-rt", [chroot], build_after_id=llvm_build.id)

def main() -> None:
    parser = argparse.ArgumentParser(description='Start LLVM snapshot builds on Fedora Copr.')
    parser.add_argument('--chroots',
                        dest='chroots',
                        metavar='CHROOT',
                        nargs='+',
                        default=[
                            "fedora-rawhide-x86_64",
                            "fedora-rawhide-aarch64", 
                            "fedora-rawhide-s390x",
                            "fedora-rawhide-ppc64le", 
                            "fedora-34-x86_64", 
                            "fedora-34-aarch64",
                            "fedora-34-s390x",
                            "fedora-34-ppc64le", 
                            "fedora-35-x86_64", 
                            "fedora-35-aarch64", 
                            "fedora-35-s390x",
                            "fedora-35-ppc64le"
                        ],
                        type=str,
                        help="list of chroots to build in")
    parser.add_argument('--packagenames',
                        dest='packagenames',
                        metavar='PACKAGENAME',
                        nargs='+',
                        default="all",
                        type=str,
                        help="list of LLVM packagenames to build in order; defaults to: all")
    parser.add_argument('--yyyymmdd',
                        dest='yyyymmdd',
                        default=datetime.date.today().strftime("%Y%m%d"),
                        type=str,
                        help="year month day combination to build for; defaults to today (e.g. {})".format(datetime.date.today().strftime("%Y%m%d")))
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
    parser.add_argument('--delete-project',
                        dest='delete_project',
                        default=False,
                        type=bool,
                        help="whether to delete the project and it's builds before building)")
    args = parser.parse_args()

    builder = CoprBuilder(ownername=args.ownername, projectname=args.projectname)
    
    # For location see see https://stackoverflow.com/a/4060259
    location = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
    
    description = open(os.path.join(location, "project-description.md"), "r").read()
    instructions = open(os.path.join(location, "project-instructions.md"), "r").read()
    custom_script = open(os.path.join(location, "custom-script.sh.tpl"), "r").read()

    builder.make_or_edit_project(description=description, instructions=instructions, chroots=args.chroots, delete_project=args.delete_project)

    packagenames = ["python-lit", "llvm", "lld", "clang", "compiler-rt", "compat-llvm", "compat-clang"]
    if args.packagenames != "all" and args.packagenames != "":
        packagenames = args.packagenames
    builder.make_packages(yyyymmdd=args.yyyymmdd, custom_script=custom_script, packagenames=packagenames)

    if args.packagenames != "all" and args.packagenames != "":
        builder.build_all(chroots=args.chroots, with_compat=True)
    else:
        builder.build_packages_chained(packagenames=args.packagenames, chroots=args.chroots)

if __name__ == "__main__":
    main()
