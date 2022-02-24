#!/bin/sh -l

set -ex

echo "Hello $1"
pwd
env
time=$(date)
echo "::set-output name=time::$time"