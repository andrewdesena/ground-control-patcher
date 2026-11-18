#!/usr/bin/env bash
# prose-lint - flags AI-tell writing tics in prose/content files.
# Usage: prose-lint.sh [file-or-dir ...]   (defaults to current dir)
#
# Two rule classes:
#   HARD  - always fix in client-facing/public content. Fails the build (exit 1).
#   SOFT  - review each hit; often legitimate. Warns only (does not fail).
#
# Rules:
#   HARD  em-dash (U+2014)  - banned in client-facing/public content
#   SOFT  the word "actually" - limit in public-facing copy (reads pretentious)
#
# Ignore: a `.prose-lintignore` file (gitignore-style globs, one per line) in the
# current dir or any scanned dir skips matching files. Use it for internal notes
# where em-dashes are fine.
#
# It is a proofreader, not a judge: review each hit and decide.

set -u

HARD_RULES=(
  "em-dash|—"
)
SOFT_RULES=(
  "word 'actually'|\bactually\b"
)

EXT_RE='\.(md|markdown|html|htm|txt|jsx|tsx|js|ts|mjs|cjs|css|scss|json|yaml|yml|xml|svg|astro|vue|svelte)$'

TARGETS=("$@")
if [ ${#TARGETS[@]} -eq 0 ]; then
  TARGETS=(".")
fi

# Build ignore patterns from any .prose-lintignore files in the tree.
IGNORE=""
while IFS= read -r ig; do
  [ -z "$ig" ] && continue
  IGNORE="$IGNORE|$ig"
done < <(find "${TARGETS[@]}" -name .prose-lintignore -type f 2>/dev/null | xargs cat 2>/dev/null)
IGNORE="${IGNORE#|}"

FILES=$(find "${TARGETS[@]}" -type f \( -path '*/.git/*' -o -path '*/node_modules/*' -o -path '*/dist/*' -o -path '*/build/*' -o -path '*/.next/*' -o -path '*/vendor/*' -o -path '*/.vercel/*' -o -path '*/.agents/*' -o -path '*/.hermes/*' \) -prune -o -type f -print 2>/dev/null | grep -E "$EXT_RE")

if [ -n "$IGNORE" ]; then
  FILES=$(printf '%s\n' "$FILES" | grep -v -E "$IGNORE")
fi

if [ -z "$FILES" ]; then
  echo "prose-lint: no content files found to scan."
  exit 0
fi

scan() {
  local label="$1" pat="$2" f line hits
  for f in $FILES; do
    hits=$(grep -n -i -E "$pat" "$f" 2>/dev/null)
    if [ -n "$hits" ]; then
      while IFS= read -r line; do
        echo "$f: [$label] $line"
      done <<< "$hits"
    fi
  done
}

hard=0
soft=0

for rule in "${HARD_RULES[@]}"; do
  out=$(scan "${rule%%|*}" "${rule#*|}")
  if [ -n "$out" ]; then printf '%s\n' "$out"; fi
  hard=$((hard + $(printf '%s\n' "$out" | grep -c .)))
done

for rule in "${SOFT_RULES[@]}"; do
  out=$(scan "${rule%%|*}" "${rule#*|}")
  if [ -n "$out" ]; then printf '%s\n' "$out"; fi
  soft=$((soft + $(printf '%s\n' "$out" | grep -c .)))
done

echo
if [ "$hard" -gt 0 ]; then
  echo "prose-lint: $hard HARD hit(s) (em-dashes). Fix before shipping client-facing content."
  exit 1
fi
if [ "$soft" -gt 0 ]; then
  echo "prose-lint: $soft SOFT hit(s) ('actually'). Review each; most are fine."
  exit 0
fi
echo "prose-lint: clean."
exit 0