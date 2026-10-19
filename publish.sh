#!/bin/bash
set -e; cd /workspace/gold-dashboard; (timeout 150 python3 mtf.py && python3 smc.py) || echo "mtf/smc skipped"; python3 edge.py || echo "edge skipped"; python3 build.py
git add i18n.js README_DATA.md signup.html exness-qr.svg exness-qr.png logo.svg icon-192.png icon-512.png knowledge.md lessons.md history .nojekyll line-bot call.html control.html gkey.js candles.json pgx.js mtf.py smc.py edge.py richmenu.png index.html build.py data.json view.json template.html publish.sh .gitignore; git commit -m "update $(date '+%F %H:%M')" || true; git push origin main
