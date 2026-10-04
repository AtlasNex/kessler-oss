#!/bin/bash
# Local driver: stream the key line + the remote script into one ssh session. The remote
# shell reads the first line as the key, then executes the rest as the script. The key never
# appears in argv, local files, or command output.
HERE="$(cd "$(dirname "$0")" && pwd)"
{ python "C:/Users/sanja/AppData/Local/hermes/scripts/el-key-mint.py"; printf '\n'; cat "$HERE/el-gen-remote.sh"; } \
  | ssh -T -o ConnectTimeout=15 root@13.140.59.39 'read -r K; export K; bash'
