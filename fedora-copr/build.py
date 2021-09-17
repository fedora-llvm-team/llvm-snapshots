#!/usr/bin/env python3

from . import CoprBuilder
import datetime
import argparse
import os

def main() -> None:
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
                        default="",
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

    builder.make_or_edit_project(description=description, instructions=instructions)
    builder.make_packages(yyyymmdd=args.yyyymmdd, custom_script=custom_script, packagenames=args.packagenames)
    
    if args.packagenames == "":
        builder.build_all(chroots=args.chroots)
    else:
        builder.build_packages_chained(packagenames=args.packagenames, chroots=args.chroots)

if __name__ == "__main__":
    main()
