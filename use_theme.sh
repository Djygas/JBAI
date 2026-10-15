#!/usr/bin/env bash
# Переключение оформления JBAI: bash use_theme.sh business|hacker|jb
# Копирует выбранную тему в frontend/ (вид меняется, логика и backend не трогаются).
# Применить на сервере: bash use_theme.sh jb && docker compose up -d --build nginx
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
THEMES_DIR="$ROOT/frontend-themes"

usage() {
  echo "Использование: bash use_theme.sh <тема>"
  echo "Доступные темы: $(ls "$THEMES_DIR" 2>/dev/null | tr '\n' ' ')"
  exit 1
}

[ $# -eq 1 ] || usage
THEME="$1"
[ -d "$THEMES_DIR/$THEME" ] || { echo "Нет такой темы: $THEME"; usage; }

# сохранить текущую как резервную (первый переключатель делает backup)
if [ ! -f "$ROOT/.theme_backup_done" ]; then
  mkdir -p "$ROOT/.frontend_backup"
  cp -f "$ROOT/frontend/index.html" "$ROOT/frontend/style.css" "$ROOT/frontend/script.js" "$ROOT/.frontend_backup/" 2>/dev/null || true
  touch "$ROOT/.theme_backup_done"
fi

cp -f "$THEMES_DIR/$THEME/index.html" "$ROOT/frontend/index.html"
cp -f "$THEMES_DIR/$THEME/style.css"  "$ROOT/frontend/style.css"
cp -f "$THEMES_DIR/$THEME/script.js"  "$ROOT/frontend/script.js"

echo "Оформление переключено: $THEME"
echo "Файлы: frontend/{index.html,style.css,script.js}"
echo "Применить на сервере: docker compose up -d --build nginx   (или просто обновить страницу — статика читается с диска)"
