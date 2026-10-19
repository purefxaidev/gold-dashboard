#!/bin/bash
set -e; cd /workspace/gold-dashboard; python3 build.py
git add index.html build.py data.json publish.sh; git commit -m "update $(date '+%F %H:%M')" || true; git push origin main
