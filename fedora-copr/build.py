#!/usr/bin/env python3

import datetime
import argparse
import os
from copr.v3 import Client, CoprRequestException, CoprNoResultException
import os
import sys

class CoprAccess(object):
    """
    This class simplifies the creation of the copr project and packages as well
    as builds.
    """

    def __init__(self, ownername: str, projectname: str, delete_after_days:int = 0):
        """
        Creates a CoprAccess object for the given owner/group and project name.

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
        self.__chroots = None
        self.__runtime_deps = "https://download.copr.fedorainfracloud.org/results/%40fedora-llvm-team/llvm-compat-packages/fedora-$releasever-$basearch"
        self.__delete_after_days = delete_after_days

    @property
    def ownername(self) -> str:
        return self.__ownername

    @property
    def projectname(self) -> str:
        return self.__projectname

    @property
    def ownerProject(self) -> str:
        return "{}/{}".format(self.ownername, self.projectname)

    @property
    def chroots(self) -> list[str]:
        return self.__chroots

    @property
    def runtime_dependencies(self) -> str:
        """ List of external repositories (== dependencies, specified as
            baseurls) that will be automatically enabled together with this
            project repository. """
        return self.__runtime_deps

    @property
    def delete_after_days(self) -> int:
        if self.__delete_after_days == 0:
            return None
        return self.__delete_after_days

    def fork_from(self, ownerProject:str) -> None:
        """
        Forks the project from the given owner/project name.
        """
        srcOwner, srcProject = ownerProject.split("/")
        self.__client.project_proxy.fork(
            ownername=srcOwner,
            projectname=srcProject,
            dstownername=self.ownername,
            dstprojectname=self.projectname, confirm=True)

    def make_or_edit_project(self, description: str, instructions: str, chroots: list[str]) -> None:
        """
        Creates the copr project or ensures that it already exists and edits it.

        :param str description: a descriptive text of the project to create or edit
        :param str instructions: a text for the instructions of how to enable this project
        """               
        existingprojects = self.__client.project_proxy.get_list(self.ownername)
        ownername = [p.name for p in existingprojects]
        if self.projectname in existingprojects:
            print("Found project {}. Updating...".format(self.ownerProject))
            
            # First get existing chroots and only add new ones 
            new_chroots = set(self.__client.project_proxy.get(ownername=self.ownername, projectname=self.projectname).chroot_repos.keys())
            diff_chroots = set(chroots).difference(new_chroots)
            if diff_chroots != set():
                print("Adding these chroots to the project: {}".format(diff_chroots))
            new_chroots.update(chroots)

            self.__client.project_proxy.edit(
                projectname=self.ownername,
                ownername=self.projectname,
                description=description,
                instructions=instructions,
                enable_net=True,
                multilib=True,
                chroots=list(new_chroots),
                devel_mode=True,
                appstream=False,
                runtime_dependencies=self.runtime_dependencies,
                delete_after_days=self.delete_after_days)
        else:
            print("Creating project {}".format(self.ownerProject))
            # NOTE: devel_mode=True means that one has to manually create the repo.
            self.__client.project_proxy.add(
                ownername=self.ownername,
                projectname=self.projectname,
                chroots=chroots,
                description=description,
                instructions=instructions,
                enable_net=True,
                multilib=True,
                devel_mode=True,
                appstream=False,
                runtime_dependencies=self.runtime_dependencies,
                delete_after_days=self.delete_after_days)

    def make_packages(self, yyyymmdd: str, packagenames: list[str], max_num_builds: int):
        """
        Creates or edits existing packages in the copr project.

        :param str yyyymmdd: the date in backwards order for which to create the package
            this refers to the date for which the source snapshot will be taken.
        :param list[str] packagenames: these packages will be created
        :param int max_num_builds maximum number of builds to keep (I know, fuzzy) 
        """

        # Ensure all packages are either created or edited if they already exist
        packages = self.__client.package_proxy.get_list(
            ownername=self.ownername, projectname=self.projectname)
        existingpackagenames = [p.name for p in packages]

        for packagename in packagenames:
            packageattrs = {
                "ownername": self.ownername,
                "projectname": self.projectname,
                "packagename": packagename,
                # See https://python-copr.readthedocs.io/en/latest/client_v3/package_source_types.html#scm
                "source_type": "scm",
                "source_dict": {
                    "clone_url": "https://src.fedoraproject.org/rpms/"+packagename+".git",
                    "committish": "upstream-snapshot",
                    "spec": packagename + ".spec",
                    "scm_type": "git",
                    "source_build_method": "make_srpm",
                }
            }
            if packagename in existingpackagenames:
                print("Resetting and editing package {} in {}".format(packagename,
                      self.ownerProject))
                self.__client.package_proxy.reset(
                    ownername=self.ownername, projectname=self.projectname, packagename=packagename)
                self.__client.package_proxy.edit(**packageattrs)
            else:
                print("Creating package {} in {}".format(packagename,
                      self.ownerProject))
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
        try:
            print("Creating build for package {} in {} for chroots {} (build after: {})".format(package_name,
                    self.ownerProject, chroots, build_after_id), end='')
            
            print("Adjusting chroots to have --with=snapshot_build and llvm-snapshot-builder package installed")
            for chroot in chroots:
                self.__client.project_chroot_proxy.edit(
                    ownername=self.ownername,
                    projectname=self.projectname,
                    chrootname=chroot,
                    with_opts="snapshot_build",
                    additional_repos=[
                        "https://download.copr.fedorainfracloud.org/results/%40fedora-llvm-team/llvm-snapshot-builder/"+ chroot,
                        "https://download.copr.fedorainfracloud.org/results/%40fedora-llvm-team/llvm-compat-packages/"+ chroot,
                    ],
                    additional_packages="llvm-snapshot-builder"
                )
            build = self.__client.package_proxy.build(
                ownername=self.ownername,
                projectname=self.projectname,
                packagename=package_name,
                # See https://python-copr.readthedocs.io/en/latest/client_v3/build_options.html
                buildopts={
                    "timeout": 30*3600,
                    "chroots": list(set(chroots)),
                    "after_build_id": build_after_id
                },
            )
        except CoprRequestException as ex:
            print("\nERROR: {}".format(ex))
            sys.exit(-1)
        print(" (build-id={}, state={})".format(build.id, build.state))
        return build

    def build_all(self, chroots: list[str], wait_on_build_id:int=None) -> None:
        """
        Builds everyting for the given chroots and creates optimal Copr batches.
        See https://docs.pagure.org/copr.copr/user_documentation.html#build-batches.
        
        NOTE: We kick-off builds for each chroot individually so that an x86_64 build
        doesn't have to wait for a potentially slower s390x build.

        :param list[str] chroots: the chroots for which the packages will be built
        :param int wait_on_build_id: the build to wait for before starting the new builds.
        """
        for chroot in chroots:
            print("CHROOT: {}".format(chroot))
            python_lit_build = self.__build_package("python-lit", [chroot])
            llvm_build = self.__build_package("llvm", [chroot], build_after_id=python_lit_build.id)
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
        if refresh_cache == False and self.chroots != None:
            return self.chroots
    
        chroots = []
        try:
            chroots = self.__client.project_proxy.get(self.ownername, self.projectname).chroot_repos.keys()
        except CoprNoResultException as ex:
            # using default chroots
            pass
        finally:
            self.chroots = chroots
        return self.chroots

    def cancel_builds(self, chroots: list[str]=None, delete_builds: bool=True) -> bool:
        """
        Cancels builds with these states: "pending", "waiting", "running", "importing".
        
        :param list[str] chroots: list of chroots for which to cancel builds.
        :param bool delete_builds: delete the builds just cancelled (default True).
        """
        print("Canceling builds  builds with these states: pending, waiting, running, importing")
        try:
            builds = self.__client.build_proxy.get_list(self.ownername, self.projectname)
        except CoprNoResultException as ex:
            print("ERROR: {}".format(ex))
            return False
        delete_build_ids = []
        for build in builds:
            if build.state in {"pending", "waiting", "running", "importing"}:
                if chroots == None or not set(chroots).isdisjoint(set(build.chroots)):
                    print("Cancelling build with ID {} (package: {}, chroots: {})".format(build.id, build.source_package['name'], build.chroots))
                    delete_build_ids.append(build.id)
                    res = self.__client.build_proxy.cancel(build.id)
        if delete_builds and delete_build_ids != []:
             print("Deleting builds: {}".format(delete_build_ids))
             self.__client.build_proxy.delete_list(delete_build_ids)
        return True

    def delete_builds(self, chroots: list[str]=None) -> bool:
        """
        Deletes all builds!
        
        :param list[str] chroots: list of chroots for which to delete builds.
        """
        print("Deleting all builds!")
        try:
            builds = self.__client.build_proxy.get_list(self.ownername, self.projectname)
        except CoprNoResultException as ex:
            print("ERROR: {}".format(ex))
            return False
        delete_build_ids = []
        for build in builds:
            if chroots == None or not set(chroots).isdisjoint(set(build.chroots)):
                delete_build_ids.append(build.id)
        if delete_build_ids != []:
            print("Deleting builds: {}".format(delete_build_ids))
            self.__client.build_proxy.delete_list(delete_build_ids)
        return True

    def delete_project(self) -> bool:
        """
        Attempts to delete the project if it exists and cancels builds before.
        """
        print("Deleting project {}/{}".format(self.ownername, self.projectname))
        if self.cancel_builds() == False:
            return False
        try:
            self.__client.project_proxy.delete(self.ownername, self.projectname)
        except CoprNoResultException as ex:
            print("ERROR: {}".format(ex))
            return False
        return True

    def project_exits(self, ownername:str, projectname:str) -> bool:
        """ project_exists returns True if the project exists. """
        try:
            self.__client.project_proxy.get(ownername, projectname)
        except CoprNoResultException as ex:
            return False
        return True
    
    def regenerate_repos(self):
        self.__client.project_proxy.regenerate_repos(ownername=self.ownername, projectname=self.projectname)

def main(args) -> None:
    builder = CoprAccess(ownername=args.ownername, projectname=args.projectname, delete_after_days=args.delete_after_days)

    # For location see see https://stackoverflow.com/a/4060259
    location = os.path.realpath(os.path.join(os.getcwd(), os.path.dirname(__file__)))
    
    description = open(os.path.join(location, "project-description.md"), "r").read()
    instructions = open(os.path.join(location, "project-instructions.md"), "r").read()

    if args.regenerate_repos:
        builder.regenerate_repos()
        return 0

    if args.project_exists:
        if builder.project_exits(builder.ownername, builder.projectname):
            print("yes")
            return 0
        print("no")
        return -1

    wait_on_build_id = args.wait_on_build_id
    if wait_on_build_id == None or wait_on_build_id <= 0:
        wait_on_build_id = None

    allpackagenames = [
        "python-lit",
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

    if args.fork_from != "":
        if builder.fork_from(ownerProject=args.fork_from):
            return 0
        return -1

    if args.cancel_builds:
        if builder.cancel_builds(chroots=chroots):
            return 0
        return -1

    chroots = args.chroots
    if args.chroots == "":
        print("Please provide --chroots")
        return -1

    if args.delete_builds:
        if builder.delete_builds(chroots=chroots):
            return 0
        return -1

    if args.delete_project:
        if builder.delete_project():
            return 0
        return -1

    builder.make_or_edit_project(chroots=chroots, description=description, instructions=instructions)

    builder.make_packages(yyyymmdd=args.yyyymmdd, packagenames=packagenames, max_num_builds=args.max_num_builds)

    if args.packagenames == "all" or args.packagenames == "":
        builder.build_all(chroots=chroots, wait_on_build_id=wait_on_build_id)
    else:
        builder.build_packages_chained(chroots=chroots, packagenames=packagenames, wait_on_build_id=wait_on_build_id)
    
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Start LLVM snapshot builds on Fedora Copr.')
    parser.add_argument('--chroots',
                        dest='chroots',
                        metavar='CHROOT',
                        nargs='+',
                        default="",
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
    parser.add_argument('--fork-from',
                        dest='fork_from',
                        default="",
                        type=str,
                        help="the project to fork from (e.g. @fedora-llvm-team/llvm-snapshots-incubator")
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
    parser.add_argument('--delete-builds',
                        dest='delete_builds',
                        action="store_true",
                        help='delete builds and cancel running ones before')                        
    parser.add_argument('--delete-project',
                        dest='delete_project',
                        action="store_true",
                        help="cancel all *running* builds and delete the project, then exit (default: False)")
    parser.add_argument('--max-num-builds',
                        dest='max_num_builds',
                        default=70,
                        type=int,
                        help="keep only the specified number of the newest-by-id builds, but remember to multiply by number of chroots (default: 9x7=63))")
    parser.add_argument('--delete-after-days',
                        dest='delete_after_days',
                        default=0,
                        type=int,
                        help="delete the project to be created after a given number of days (default: 0 which means \"keep forever\")")
    parser.add_argument('--regenerate-repos',
                        dest='regenerate_repos',
                        action="store_true",
                        help="regenerates the project's repositories, then exit")
    parser.add_argument('--project-exists',
                        dest='project_exists',
                        action="store_true",
                        help="checks if the project exists, then exit")
    parser.add_argument('--version', action='version', version='%(prog)s 1.0')

    args = parser.parse_args()
    sys.exit(main(args))
