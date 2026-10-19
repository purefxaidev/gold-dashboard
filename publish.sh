#!/bin/bash
set -e; cd /workspace/gold-dashboard; python3 build.py
git add knowledge.md lessons.md history .nojekyll line-bot call.html richmenu.png index.html build.py data.json view.json template.html publish.sh .gitignore; git commit -m "update $(date '+%F %H:%M')" || true; git push origin main
