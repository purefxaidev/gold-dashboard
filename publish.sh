#!/bin/bash
set -e; cd /workspace/gold-dashboard; python3 build.py
git add i18n.js README_DATA.md signup.html exness-qr.svg exness-qr.png logo.svg icon-192.png icon-512.png knowledge.md lessons.md history .nojekyll line-bot call.html control.html richmenu.png index.html build.py data.json view.json template.html publish.sh .gitignore; git commit -m "update $(date '+%F %H:%M')" || true; git push origin main
