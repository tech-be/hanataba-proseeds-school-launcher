#!/usr/bin/env bash
# 確認用の DB（lw2_schema_check）を読む新アプリを、別の名前・別のポートで立てる・止める。
#
#   scripts/e2e-stack.sh up      バックエンド :18080・フロント :13000 を立てる
#   scripts/e2e-stack.sh down    止めて消す
#   scripts/e2e-stack.sh status  動いているかを見る
#
# **動いている開発の環境（learningware の DB・:3000・:8080）には触れない。**
# school-launcher の docker compose（プロジェクト名 school-launcher）の btoc-backend /
# btoc-frontend の定義を `run` で借り、依存（mysql・redis・mailpit など）は今動いているものを使う。
#
# 環境変数:
#   SCHOOL_LAUNCHER_DIR  school-launcher の作業ツリー（既定: 作業用の worktree）
#   LW2CHECK_DB          読ませる DB（既定: lw2_schema_check。learningware は拒む）
#   LW2CHECK_CAREER_DB   career が読む DB（既定: career_lw2_check。career は拒む）
#   LW2CHECK_SLUG        テナントのスラッグ（既定: recademy）
set -euo pipefail

SL_DIR="${SCHOOL_LAUNCHER_DIR:-$HOME/ghq/github.com/proseeds/school-launcher-lw2-rework}"
DB="${LW2CHECK_DB:-lw2_schema_check}"
CAREER_DB="${LW2CHECK_CAREER_DB:-career_lw2_check}"
SLUG="${LW2CHECK_SLUG:-recademy}"
BACKEND=lw2check-backend
CAREER=lw2check-career
FRONTEND=lw2check-frontend
BACKEND_PORT=18080
CAREER_PORT=18081
FRONTEND_PORT=13000

if [[ "$DB" == "learningware" || "$DB" != lw2_* ]]; then
  echo "LW2CHECK_DB は確認用の DB（lw2_ で始まる名前）にする: $DB" >&2
  exit 1
fi
if [[ "$CAREER_DB" == "career" || "$CAREER_DB" != career_* ]]; then
  echo "LW2CHECK_CAREER_DB は確認用の DB（career_ で始まり、career そのものではない名前）にする: $CAREER_DB" >&2
  exit 1
fi

compose() { (cd "$SL_DIR" && docker compose -p school-launcher "$@"); }

wait_for() {
  local name=$1 url=$2 header=${3:-} limit=${4:-180}
  for ((i = 0; i < limit; i += 3)); do
    code=$(curl -s -o /dev/null -w '%{http_code}' ${header:+-H "$header"} "$url" || true)
    if [[ "$code" == 200 ]]; then
      echo "$name: 応答あり ($url)"
      return 0
    fi
    sleep 3
  done
  echo "$name: ${limit} 秒待っても 200 が返らない（最後: $code）。docker logs $name を見る" >&2
  return 1
}

up() {
  if docker ps -a --format '{{.Names}}' | grep -qx "$BACKEND"; then
    echo "$BACKEND が既にある。先に down する" >&2
    exit 1
  fi
  compose run -d --no-deps --name "$BACKEND" -p "$BACKEND_PORT:8080" \
    -e LW_DATABASE_NAME="$DB" btoc-backend >/dev/null
  # career は会員の名前などを btoc の内部 API から引くので、確認用のバックエンドに向ける
  compose run -d --no-deps --name "$CAREER" -p "$CAREER_PORT:8081" \
    -e CAREER_DATABASE_NAME="$CAREER_DB" -e CAREER_LMS_BASE_URL="http://$BACKEND:8080" career-backend >/dev/null
  compose run -d --no-deps --name "$FRONTEND" -p "$FRONTEND_PORT:3000" \
    -e BTOC_BACKEND_INTERNAL_URL="http://$BACKEND:8080" \
    -e CAREER_BACKEND_INTERNAL_URL="http://$CAREER:8081" btoc-frontend >/dev/null
  wait_for "$BACKEND" "http://localhost:$BACKEND_PORT/api/v1/branding" "X-Tenant-Slug: $SLUG" 300
  wait_for "$CAREER" "http://localhost:$CAREER_PORT/" "" 300
  wait_for "$FRONTEND" "http://$SLUG.localhost:$FRONTEND_PORT/login" "" 300
  echo "URL: http://$SLUG.localhost:$FRONTEND_PORT （DB: ${DB} / career: ${CAREER_DB}）"
}

down() {
  docker rm -f "$FRONTEND" "$CAREER" "$BACKEND" >/dev/null 2>&1 || true
  echo "止めた: $FRONTEND $CAREER $BACKEND"
}

status() {
  docker ps -a --filter "name=^lw2check-" --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
}

case "${1:-}" in
  up) up ;;
  down) down ;;
  status) status ;;
  *) echo "使い方: $0 up|down|status" >&2; exit 2 ;;
esac
