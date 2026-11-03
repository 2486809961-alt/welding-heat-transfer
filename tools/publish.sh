#!/usr/bin/env bash
# 一键更新：把本地 Obsidian 库「焊接」同步到 GitHub 仓库 + 重建网站 + 发版
#
#   bash tools/publish.sh              # 同步笔记 + 重建站点 + 推 gh-pages
#   bash tools/publish.sh --release    # 额外打 zip 建一个 Release
#
# 依赖：git、python3（markdown + pyyaml）、gh token（从 macOS 钥匙串读取，或 GH_TOKEN 环境变量）
set -uo pipefail

VAULT="$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents/焊接"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OWNER="2486809961-alt"
NAME="welding-heat-transfer"

cd "$REPO_DIR" || exit 1
TOK="${GH_TOKEN:-$(printf 'protocol=https\nhost=github.com\n\n' | git credential fill 2>/dev/null | awk -F= '/^password=/{print substr($0,10)}')}"
if [ -z "${TOK}" ]; then echo "✗ 找不到 GitHub token：export GH_TOKEN=ghp_xxx"; exit 1; fi

echo "▶ 1/5 同步笔记（排除 .git / public / 插件二进制 / 原书 PDF）"
rsync -a \
  --exclude '.obsidian/plugins/*/main.js' \
  --exclude '.obsidian/plugins/*/*.map' \
  --exclude '.obsidian/plugins/*/data.json' \
  --exclude '.obsidian/plugins/*/data.json.dsh-backup' \
  --exclude '.obsidian/workspace*.json' \
  --exclude '.obsidian/cache' \
  --exclude '.obsidian-mcp' \
  --exclude '.DS_Store' --exclude '.trash' --exclude '*.dsh-backup' \
  "$VAULT/" "$REPO_DIR/"

echo "▶ 2/5 提交并推送 main"
git remote set-url origin "https://x-access-token:${TOK}@github.com/${OWNER}/${NAME}.git"
git add -A
if git diff --cached --quiet; then
  echo "  · 无变更"
else
  git commit -q -m "sync: $(date '+%Y-%m-%d %H:%M') 笔记更新"
  git push -q origin main && echo "  ✓ main 已更新"
fi
git remote set-url origin "https://github.com/${OWNER}/${NAME}.git"

echo "▶ 3/5 重建静态站点"
python3 tools/build_site.py | tail -2

echo "▶ 4/5 推送 gh-pages"
cd "$REPO_DIR/public" || exit 1
rm -rf .git
git init -q -b gh-pages
git config user.name "KIM"
git config user.email "271341795+${OWNER}@users.noreply.github.com"
git config core.quotepath false
git add -A && git commit -q -m "site: $(date '+%Y-%m-%d %H:%M') 重建"
git remote add origin "https://x-access-token:${TOK}@github.com/${OWNER}/${NAME}.git"
git push -q -f origin gh-pages && echo "  ✓ gh-pages 已更新 → https://${OWNER}.github.io/${NAME}/"
cd "$REPO_DIR" || exit 1

if [ "${1:-}" = "--release" ]; then
  echo "▶ 5/5 打包 zip 并发 Release"
  STAGE=$(mktemp -d)
  mkdir -p "$STAGE/stage/焊接"
  rsync -a --exclude '.git' --exclude 'public' --exclude 'tools' --exclude 'README.md' \
    --exclude '.gitignore' --exclude '*.pdf' --exclude '.obsidian/plugins/*/main.js' \
    --exclude '.obsidian/plugins/*/*.map' --exclude '.obsidian/plugins/*/data.json' \
    --exclude '.obsidian/workspace*.json' --exclude '.DS_Store' --exclude '.obsidian-mcp' \
    "$REPO_DIR/" "$STAGE/stage/焊接/"
  ( cd "$STAGE/stage" && zip -qr "$STAGE/vault.zip" 焊接 )
  TAG="v$(date '+%Y.%m.%d-%H%M')"
  RID=$(curl -s -X POST -H "Authorization: Bearer ${TOK}" -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/${OWNER}/${NAME}/releases" \
    -d "{\"tag_name\":\"${TAG}\",\"name\":\"焊接传热学知识库 ${TAG}\",\"draft\":false,\"prerelease\":false}" \
    | python3 -c "import sys,json;print(json.load(sys.stdin).get('id',''))")
  if [ -n "$RID" ]; then
    curl -s -o /dev/null -X POST -H "Authorization: Bearer ${TOK}" -H "Content-Type: application/zip" \
      --data-binary @"$STAGE/vault.zip" \
      "https://uploads.github.com/repos/${OWNER}/${NAME}/releases/${RID}/assets?name=welding-heat-transfer-vault.zip"
    echo "  ✓ Release ${TAG} 已发布"
  fi
  rm -rf "$STAGE"
fi

echo
echo "网站：https://${OWNER}.github.io/${NAME}/"
echo "仓库：https://github.com/${OWNER}/${NAME}"