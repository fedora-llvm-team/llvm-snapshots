#!/usr/bin/env python3

import datetime
import argparse
import os
from copr.v3 import Client, CoprRequestException, CoprNoResultException
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
        self.__default_chroots = [
            "fedora-rawhide-x86_64",
            "fedora-rawhide-aarch64", 
            "fedora-rawhide-s390x",
            "fedora-rawhide-ppc64le",
            "fedora-rawhide-i386", 
            "fedora-34-x86_64", 
            "fedora-34-aarch64",
            "fedora-34-s390x",
            "fedora-34-ppc64le", 
            "fedora-34-i386", 
            "fedora-35-x86_64", 
            "fedora-35-aarch64", 
            "fedora-35-s390x",
            "fedora-35-ppc64le",
            "fedora-35-i386"
        ]
        self.__chroots = None

    def make_or_edit_project(self, description: str, instructions: str, chroots: list[str]) -> None:
        """
        Creates the copr project or ensures that it already exists and edits it.

        :param str description: a descriptive text of the project to create or edit
        :param str instructions: a text for the instructions of how to enable this project
        """               
        existingprojects = self.__client.project_proxy.get_list(self.__ownername)
        existingprojectnames = [p.name for p in existingprojects]
        if self.__projectname in existingprojectnames:
            print("Found project {}/{}. Updating...".format(self.__ownername, self.__projectname))
            
            # First get existing chroots and only add new ones 
            new_chroots = set(self.__client.project_proxy.get(ownername=self.__ownername, projectname=self.__projectname).chroot_repos.keys())
            diff_chroots = set(chroots).difference(new_chroots)
            if diff_chroots != set():
                print("Adding these chroots to the project: {}".format(diff_chroots))
            new_chroots.update(chroots)

            self.__client.project_proxy.edit(
                ownername=self.__ownername,
                projectname=self.__projectname,
                description=description,
                instructions=instructions,
                enable_net=True,
                multilib=True,
                chroots=list(new_chroots),
                devel_mode=True,
                appstream=False)
        else:
            print("Creating project {}/{}".format(self.__ownername, self.__projectname))
            # NOTE: devel_mode=True means that one has to manually create the repo.
            self.__client.project_proxy.add(
                ownername=self.__ownername,
                projectname=self.__projectname,
                chroots=chroots,
                description=description,
                instructions=instructions,
                enable_net=True,
                multilib=True,
                devel_mode=True,
                appstream=False)

    def make_packages(self, yyyymmdd: str, custom_script: str, packagenames: list[str], max_num_builds: int):
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
                    "resultdir": "buildroot",
                    "max_builds": max_num_builds,
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

    def build_packages_chained(self, packagenames: list[str], chroots: list[str], wait_on_build_id:int=None) -> None:
        """
        Builds the list of packages for the given chroots in the order they are given.
        
        NOTE: We kick-off builds for each chroot individually so that an x86_64 build
        doesn't have to wait for a potentially slower s390x build.

        :param list[str] packagenames: the packages to be built
        :param list[str] chroots: the chroots for which the packages will be built
        """
        for chroot in chroots:
            print("CHROOT: {}".format(chroot))
            previous_build_id = wait_on_build_id
            for packagename in packagenames:
                build = self.__build_package(packagename, [chroot], build_after_id=previous_build_id)
                if build != dict():
                    previous_build_id = build.id
                    print(" (build-id={}, state={})".format(previous_build_id, build.state))
                else:
                    print("skipped build of package {} in chroot {}".format(packagename, chroot))

    def __build_package(self, package_name: str, chroots: list[str], build_after_id: int=None):
        build = None

        # Don't build compat packages in chroots where they don't belong.
        # TODO(kwk): Oh boy, this sucks.
        new_chroots = set(chroots)
        for chroot in chroots:
            if (package_name == "compat-llvm-fedora-34" or package_name == "compat-clang-fedora-34" ) and not chroot.startswith("fedora-34-"):
                new_chroots.remove(chroot)
            if (package_name == "compat-llvm-fedora-35" or package_name == "compat-clang-fedora-35" ) and not chroot.startswith("fedora-35-"):
                new_chroots.remove(chroot)
            if (package_name == "compat-llvm-fedora-rawhide" or package_name == "compat-clang-fedora-rawhide" ) and not chroot.startswith("fedora-rawhide-"):
                new_chroots.remove(chroot)
        if new_chroots == set():
            return dict()

        try:
            print("Creating build for package {} in {}/{} for chroots {} (build after: {})".format(package_name,
                    self.__ownername, self.__projectname, chroots, build_after_id), end='')
            build = self.__client.package_proxy.build(
                ownername=self.__ownername,
                projectname=self.__projectname,
                packagename=package_name,
                # See https://python-copr.readthedocs.io/en/latest/client_v3/build_options.html
                buildopts={
                    "timeout": 30*3600,
                    "chroots": list(new_chroots),
                    "after_build_id": build_after_id
                },
            )
        except CoprRequestException as ex:
            print("\nERROR: {}".format(ex))
            sys.exit(-1)
        print(" (build-id={}, state={})".format(build.id, build.state))
        return build

    def build_all(self, chroots: list[str], with_compat:bool=False, wait_on_build_id:int=None) -> None:
        """
        Builds everyting for the given chroots and creates optimal Copr batches.
        See https://docs.pagure.org/copr.copr/user_documentation.html#build-batches.
        
        NOTE: We kick-off builds for each chroot individually so that an x86_64 build
        doesn't have to wait for a potentially slower s390x build.

        :param list[str] chroots: the chroots for which the packages will be built
        :param bool with_compat: whether to build compatibility packages or not
        :param int wait_on_build_id: the build to wait for before starting the new builds.
        """
        for chroot in chroots:
            print("CHROOT: {}".format(chroot))
            python_lit_build = self.__build_package("python-lit", [chroot])
            llvm_compat_build = wait_on_build_id
            clang_compat_build = wait_on_build_id
            if with_compat == True:
                llvm_compat_build = dict()
                clang_compat_build = dict()

                llvm_compat_build = self.__build_package("compat-llvm-fedora-34", [chroot], build_after_id=python_lit_build.id)
                if llvm_compat_build != dict():
                    clang_compat_build = self.__build_package("compat-clang-fedora-34", [chroot], build_after_id=llvm_compat_build.id)

                if llvm_compat_build == dict():
                    llvm_compat_build = self.__build_package("compat-llvm-fedora-35", [chroot], build_after_id=python_lit_build.id)
                    if llvm_compat_build != dict():
                        clang_compat_build = self.__build_package("compat-clang-fedora-35", [chroot], build_after_id=llvm_compat_build.id)

                if llvm_compat_build == dict():
                    llvm_compat_build = self.__build_package("compat-llvm-fedora-rawhide", [chroot], build_after_id=python_lit_build.id)
                    if llvm_compat_build != dict():
                        clang_compat_build = self.__build_package("compat-clang-fedora-rawhide", [chroot], build_after_id=llvm_compat_build.id)


            llvm_build = self.__build_package("llvm", [chroot], build_after_id=llvm_compat_build.id if with_compat else python_lit_build.id)
            lld_build = self.__build_package("lld", [chroot], build_after_id=llvm_build.id)
            mlir_build = self.__build_package("mlir", [chroot], build_after_id=llvm_build.id)
            clang_build = self.__build_package("clang", [chroot], build_after_id=llvm_build.id)
            libomp_build = self.__build_package("libomp", [chroot], build_after_id=clang_build.id)
            compiler_rt_build = self.__build_package("compiler-rt", [chroot], build_after_id=llvm_build.id)

    def get_chroots(self, refresh_cache:bool=False) -> list[str]:
        """
        Returns the list of chroots associated with a given project uses default ones.
        Subsequent calls will return a cached version of the list.
        """
        if refresh_cache == False and self.__chroots != None:
            return self.__chroots
    
        chroots = self.__default_chroots
        try:
            chroots = self.__client.project_proxy.get(self.__ownername, self.__projectname).chroot_repos.keys()
        except CoprNoResultException as ex:
            # using default chroots
            pass
        finally:
            self.__chroots = chroots
        return self.__chroots

    def cancel_builds(self) -> bool:
        """
        Cancels builds with these states: "pending", "waiting", "running", "importing".
        """
        print("Canceling builds  builds with these states: pending, waiting, running, importing")
        try:
            builds = self.__client.build_proxy.get_list(self.__ownername, self.__projectname)
        except CoprNoResultException as ex:
            print("ERROR: {}".format(ex))
            return False
        for build in builds:
            if build.state in {"pending", "waiting", "running", "importing"}:
                print("Cancelling build with ID  {}".format(build.id))
                self.__client.build_proxy.cancel(build.id)
        return True

    def delete_project(self) -> bool:
        """
        Attempts to delete the project if it exists and cancels builds before.
        """
        print("Deleting project {}/{}".format(self.__ownername, self.__projectname))
        if self.cancel_builds() == False:
            return False
        try:
            self.__client.project_proxy.delete(self.__ownername, self.__projectname)
        except CoprNoResultException as ex:
            print("ERROR: {}".format(ex))
            return False
        return True
    
    def regenerate_repos(self):
        self.__client.project_proxy.regenerate_repos(ownername=self.__ownername, projectname=self.__projectname)

def main(args) -> None:
    builder = CoprBuilder(ownername=args.ownername, projectname=args.projectname)

    # For location see see https://stackoverflow.com/a/4060259
    location = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
    
    description = open(os.path.join(location, "project-description.md"), "r").read()
    instructions = open(os.path.join(location, "project-instructions.md"), "r").read()
    custom_script = open(os.path.join(location, "custom-script.sh.tpl"), "r").read()

    if args.regenerate_repos:
        builder.regenerate_repos()
        sys.exit(0)

    wait_on_build_id = args.wait_on_build_id
    if wait_on_build_id == None or wait_on_build_id <= 0:
        wait_on_build_id = None

    allpackagenames = [
        "python-lit",
        "compat-llvm-fedora-rawhide",
        "compat-llvm-fedora-35",
        "compat-llvm-fedora-34",
        "compat-clang-fedora-rawhide",
        "compat-clang-fedora-35",
        "compat-clang-fedora-34",
        "llvm",
        "compiler-rt",
        "lld",
        "clang",
        "mlir",
        "libomp"
    ]
    if args.packagenames == ["all"] or args.packagenames == "all" or args.packagenames == "":
        packagenames = allpackagenames
    else:
        packagenames = args.packagenames

    chroots = args.chroots
    if args.chroots == ["all"] or args.chroots == "all" or args.chroots == "":
        chroots = builder.get_chroots()

    if args.print_config == True:
        print("""
Summary
=======

Owner/Group name:   {} 
Project name:       {}
Package names:      {}
Chroots:            {}
Wait on build ID:   {} 
Timeout:            {}
Year month day:     {}

Description:
------------
{}

Instructions:
-------------
{}

Custom_script:
--------------
{}
""".format(
        args.ownername, 
        args.projectname, 
        packagenames, 
        chroots,
        wait_on_build_id,
        args.timeout,
        args.yyyymmdd,
        description, 
        instructions, 
        custom_script))
        sys.exit(0)

    if args.cancel_builds:
        res = builder.cancel_builds()
        sys.exit(0 if res == True else -1)

    if args.delete_project:
        res = builder.delete_project()
        sys.exit(0 if res == True else -1)

    builder.make_or_edit_project(chroots=chroots, description=description, instructions=instructions)

    builder.make_packages(yyyymmdd=args.yyyymmdd, custom_script=custom_script, packagenames=packagenames, max_num_builds=args.max_num_builds)

    if args.packagenames == "all" or args.packagenames == "":
        builder.build_all(chroots=chroots, with_compat=args.with_compat, wait_on_build_id=wait_on_build_id)
    else:
        builder.build_packages_chained(chroots=chroots, packagenames=packagenames, wait_on_build_id=wait_on_build_id)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Start LLVM snapshot builds on Fedora Copr.')
    parser.add_argument('--chroots',
                        dest='chroots',
                        metavar='CHROOT',
                        nargs='+',
                        default="all",
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
                        default='@fedora-llvm-team',
                        type=str,
                        help="owner (or group) name of the copr project to be created or checked for existence (defaults to: @fedora-llvm-team)")
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
    parser.add_argument('--wait-on-build-id',
                        dest='wait_on_build_id',
                        default=None,
                        type=int,
                        help="wait on the given build ID before starting the build")
    parser.add_argument('--cancel-builds',
                        dest='cancel_builds',
                        action="store_true",
                        help='cancel builds with these states before creating new ones and then exits: "pending", "waiting", "running", "importing"')
    parser.add_argument('--print-config',
                        dest='print_config',
                        action="store_true",
                        help="print the parsed config and exit (default: False)")
    parser.add_argument('--without-compat',
                        dest='with_compat',
                        action="store_false",
                        help="don't build the compat packages (default: no)")
    parser.add_argument('--with-compat',
                        dest='with_compat',
                        action="store_true",
                        help="build the compat packages (default: yes)")
    parser.add_argument('--delete-project',
                        dest='delete_project',
                        action="store_true",
                        help="cancel all *running* builds and delete the project, then exit (default: False)")
    parser.add_argument('--max-num-builds',
                        dest='max_num_builds',
                        default=70,
                        type=int,
                        help="keep only the specified number of the newest-by-id builds, but remember to multiply by number of chroots (default: 9x7=63))")
    parser.add_argument('--regenerate-repos',
                        dest='regenerate_repos',
                        action="store_true",
                        help="regenerates the project's repositories, then exit")

    args = parser.parse_args()
    main(args)
