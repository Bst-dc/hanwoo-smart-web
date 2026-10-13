#!/usr/bin/env bash
# 스마트컨설팅 기본 주소를 새 앱(FastAPI)으로 바꾼다 — 시험농장(testfarm → testfarm-next)과 같은 방식.
#
#   바꾸기:  sudo bash switch.sh
#   되돌리기: sudo bash switch.sh --rollback
#
# 바꾼 뒤 주소:
#   consulting.<BASE_HOST>       → 새 앱 (consulting-next 컨테이너)
#   consulting-next.<BASE_HOST>  → 새 앱 (지금 주소도 그대로 쓸 수 있음)
#   consulting-old.<BASE_HOST>   → 기존 Streamlit 앱 (되돌릴 때를 대비해 남겨 둠)
#
# Caddyfile 만 고친다. 컨테이너·DB·update.sh 는 건드리지 않는다.
# 고치기 전에 Caddyfile 을 백업하고, Caddy 가 새 설정을 거부하면 백업으로 되돌린 뒤 멈춘다.
set -euo pipefail

DEPLOY=/opt/hanwoo/deploy
cd "$DEPLOY"
stamp=$(date +%Y%m%d-%H%M%S)
mode=${1:-switch}

case "$mode" in
  switch|--rollback) ;;
  *) echo "사용법: sudo bash switch.sh [--rollback]"; exit 2 ;;
esac

cp -p Caddyfile "Caddyfile.bak-$stamp"
echo "백업: $DEPLOY/Caddyfile.bak-$stamp"

new=$(mktemp "$DEPLOY/Caddyfile.new.XXXX")
python3 - "$mode" "$new" <<'EOF'
import re, sys
mode, out = sys.argv[1], sys.argv[2]
text = open("Caddyfile", encoding="utf-8").read()

def block(header):
    """header 로 시작하는 사이트 블록 하나(주석 줄 포함 안 함)를 찾는다. 없으면 None."""
    m = re.search(r"^" + re.escape(header) + r" \{\n(?:.*\n)*?\}\n?", text, re.M)
    return m

OLD_ONLY = "consulting.{$BASE_HOST}"
NEXT_ONLY = "consulting-next.{$BASE_HOST}"
BOTH = "consulting.{$BASE_HOST}, consulting-next.{$BASE_HOST}"
OLD_ADDR = "consulting-old.{$BASE_HOST}"

if mode == "switch":
    if block(BOTH):
        print("이미 새 앱으로 바뀌어 있습니다. 바꿀 것이 없습니다."); open(out, "w").write(text); sys.exit(0)
    a, b = block(OLD_ONLY), block(NEXT_ONLY)
    assert a and "reverse_proxy consulting:8501" in a.group(0), "Caddyfile 에서 기존 consulting 주소 블록을 못 찾았습니다"
    assert b and "reverse_proxy consulting-next:8000" in b.group(0), "Caddyfile 에서 consulting-next 주소 블록을 못 찾았습니다"
    text = text.replace(b.group(0), "")
    # 새 앱 블록 위의 설명 주석 한 줄도 같이 지운다 (있으면)
    text = text.replace("\n# 스마트컨설팅 새 앱(FastAPI, 모바일 화면) — 기존 consulting 주소(Streamlit)는 그대로 둔다.\n", "\n")
    text = text.replace(a.group(0),
        "# 스마트컨설팅: 기본 주소는 새 앱(FastAPI). 이전 Streamlit 앱은 되돌릴 때를 대비해 consulting-old 주소에 남겨 둔다.\n"
        f"{BOTH} {{\n        reverse_proxy consulting-next:8000\n}}\n\n"
        f"{OLD_ADDR} {{\n        reverse_proxy consulting:8501\n}}\n")
else:
    if not block(BOTH):
        print("새 앱으로 바뀌어 있지 않습니다. 되돌릴 것이 없습니다."); open(out, "w").write(text); sys.exit(0)
    both, old = block(BOTH), block(OLD_ADDR)
    text = text.replace("# 스마트컨설팅: 기본 주소는 새 앱(FastAPI). 이전 Streamlit 앱은 되돌릴 때를 대비해 consulting-old 주소에 남겨 둔다.\n", "")
    if old:
        text = text.replace(old.group(0), "")
    text = text.replace(both.group(0),
        f"{OLD_ONLY} {{\n        reverse_proxy consulting:8501\n}}\n\n"
        f"{NEXT_ONLY} {{\n        reverse_proxy consulting-next:8000\n}}\n")
text = re.sub(r"\n{3,}", "\n\n", text)
open(out, "w", encoding="utf-8").write(text)
EOF

if cmp -s "$new" Caddyfile; then
  rm -f "$new"
  echo "Caddyfile 이 그대로라 Caddy 를 다시 읽지 않습니다."
  exit 0
fi
[ -s "$new" ]
chmod --reference=Caddyfile "$new"
mv "$new" Caddyfile
echo "--- 바뀐 내용 ---"
diff "Caddyfile.bak-$stamp" Caddyfile || true
echo "-----------------"

# Caddy 가 새 설정을 받아들이는지 먼저 검사하고, 안 되면 백업으로 되돌린다
if ! docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
  cp -p "Caddyfile.bak-$stamp" Caddyfile
  echo "⚠️ Caddy 가 새 설정을 거부해 백업으로 되돌렸습니다. 아무것도 바뀌지 않았습니다."
  docker compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile || true
  exit 1
fi
docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
host=$(grep -E '^BASE_HOST=' .env | cut -d= -f2 || true)
echo
if [ "$mode" = switch ]; then
  echo "✅ 바꿨습니다."
  echo "   새 앱:     https://consulting.${host:-<BASE_HOST>}/"
  echo "   기존 앱:   https://consulting-old.${host:-<BASE_HOST>}/  (새 주소는 인증서를 받느라 첫 접속이 몇 초 걸릴 수 있습니다)"
  echo "   되돌리기:  sudo bash /opt/hanwoo/apps/consulting/deploy/consulting-next/switch.sh --rollback"
else
  echo "✅ 되돌렸습니다. consulting 주소는 다시 기존 Streamlit 앱입니다."
fi
