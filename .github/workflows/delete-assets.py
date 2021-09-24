#!/bin/env python3

from github import Github, UnknownObjectException
import argparse
import datetime

def main(args) -> None:
    g = Github(login_or_token=args.token)
    repo = g.get_repo(args.project)
    
    print("deleting assets older than a week and from today in release '{}'".format(args.release_name))
    try:
        release = repo.get_release(args.release_name)
    except UnknownObjectException as ex:
        print("release '{}' not found and so there's nothing to delete".format(args.release_name))
    else:
        for asset in release.get_assets():
            if asset.created_at < (datetime.datetime.now() - datetime.timedelta(days=args.delete_older)):
                print("deleting asset '{}' created at {}".format(asset.name, asset.created_at))
                asset.delete_asset()
            if args.delete_today == True and asset.created_at.strftime("%Y%m%d") == datetime.datetime.now().strftime("%Y%m%d"):
                print("deleting asset '{}' created at {}".format(asset.name, asset.created_at))
                asset.delete_asset()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Delete assets from today and older than a week (by default).')
    parser.add_argument('--token',
                        dest='token',
                        type=str,
                        default="YOUR-TOKEN-HERE",
                        help="your github token")
    parser.add_argument('--project',
                        dest='project',
                        type=str,
                        default="kwk/llvm-project",
                        help="github project to use (default: kwk/llvm-project")
    parser.add_argument('--release-name',
                        dest='release_name',
                        type=str,
                        default="source-snapshot",
                        help="name of the release to store the source snapshots (default: kwk/llvm-project")    
    parser.add_argument('--delete-older',
                        dest='delete_older',
                        type=int,
                        default="7",
                        help="assets older than the given amount of days will be deleted (default: 7)")
    parser.add_argument('--delete-today',
                        dest='delete_today',
                        type=bool,
                        choices=[False,True],
                        default=True,
                        help="delete assets of today before recreating them (default: True)") 
    main(parser.parse_args())