#!/usr/bin/env bash
# Baixa as fontes da marca do Google Fonts (TTF) para a pasta indicada.
set -euo pipefail
DEST="${1:-/usr/share/fonts/truetype/fabrica}"; mkdir -p "$DEST"
for item in "Bebas+Neue|BebasNeue-Regular" "Barlow:wght@800|Barlow-ExtraBold" \
            "Barlow+Condensed:wght@700|BarlowCondensed-Bold" "Permanent+Marker|PermanentMarker-Regular"; do
  fam="${item%%|*}"; nome="${item##*|}"
  url=$(curl -fsS "https://fonts.googleapis.com/css2?family=${fam}" -A "Wget/1.0" | grep -o 'https://[^)]*\.ttf' | head -1)
  curl -fsS -o "$DEST/$nome.ttf" "$url"
done
