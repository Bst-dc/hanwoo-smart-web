#!/usr/bin/env bash
# 스마트컨설팅 새 앱(consulting-next) 서버 설정 — 한 번만 실행한다. 여러 번 실행해도 안전하다(이미 된 것은 건너뜀).
#
#   sudo bash /opt/hanwoo/apps/consulting/deploy/consulting-next/setup.sh
#
# 하는 일 (모두 /opt/hanwoo/deploy 에서, 고치기 전에 .bak-시각 으로 백업):
#   1. consulting-next.Dockerfile / .dockerignore 만들기
#   2. docker-compose.yml 에 consulting-next 서비스를 넣고 caddy 의존에 추가
#   3. Caddyfile 에 consulting-next.{$BASE_HOST} 주소 추가
#   4. update.sh 에서 consulting 이 바뀌면 consulting-next 도 같이 빌드하게 추가
#   5. 빌드·시작·Caddy 설정 다시 읽기 → 상태 확인
# 기존 consulting(Streamlit) 서비스와 주소는 건드리지 않는다. 문제가 생기면 .bak 파일로 되돌리면 된다.
set -euo pipefail

DEPLOY=/opt/hanwoo/deploy
cd "$DEPLOY"
stamp=$(date +%Y%m%d-%H%M%S)

backup() { cp -p "$1" "$1.bak-$stamp"; echo "백업: $1.bak-$stamp"; }

# ---------- 1. Dockerfile ----------
cat > consulting-next.Dockerfile <<'EOF'
# 스마트컨설팅 새 앱 (FastAPI + 모바일 HTML/JS) — Bst-dc/hanwoo-smart-web 같은 저장소, 빌드 기준 폴더 = 서버의 /opt/hanwoo/apps/consulting
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Seoul

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY api/requirements.txt api-requirements.txt
RUN pip install -r api-requirements.txt
COPY . .

# 비밀 설정(DATABASE_URL, APP_PASSWORD 등)은 이미지에 넣지 않는다. 실행할 때 /app/.streamlit/secrets.toml 로 끼워 넣는다 (docker-compose.yml).
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD curl -fsS http://localhost:8000/api/health || exit 1
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
EOF

cat > consulting-next.Dockerfile.dockerignore <<'EOF'
# 비밀·조합원 실데이터·큰 자료가 이미지에 들어가지 않게 막는다.
.git
.venv
.claude
**/__pycache__
.streamlit/secrets.toml
.env
*.db
*.db-*
*.xlsx
*.xls
reference/
knowledge/
dump.sql
migrate.py
*.bat
deploy/
EOF
echo "1. Dockerfile 준비 완료"

# ---------- 2. docker-compose.yml ----------
if grep -q '^  consulting-next:' docker-compose.yml; then
  echo "2. docker-compose.yml 에 이미 consulting-next 가 있어 건너뜀"
else
  backup docker-compose.yml
  python3 - <<'EOF'
path = "docker-compose.yml"
text = open(path, encoding="utf-8").read()

service = '''  # 스마트컨설팅 새 앱(FastAPI, 모바일 화면). 기존 consulting(Streamlit)과 같은 저장소·같은 secrets·같은 Supabase 를 쓰는 병행 운영용 — 문제가 있으면 이 서비스만 끄면 된다.
  consulting-next:
    build:
      context: /opt/hanwoo/apps/consulting
      dockerfile: /opt/hanwoo/deploy/consulting-next.Dockerfile
    restart: unless-stopped
    logging: *logging
    environment:
      COOKIE_SECURE: "1"
    volumes:
      - /opt/hanwoo/secrets/consulting.toml:/app/.streamlit/secrets.toml:ro
    mem_limit: 500m

'''
marker = "  caddy:\n"
assert text.count(marker) == 1, "caddy 서비스 위치를 못 찾았습니다"
text = text.replace(marker, service + marker)

dep = "      - testfarm-next\n"
assert text.count(dep) == 1, "caddy depends_on 위치를 못 찾았습니다"
text = text.replace(dep, dep + "      - consulting-next\n")
open(path, "w", encoding="utf-8").write(text)
EOF
  echo "2. docker-compose.yml 수정 완료"
fi

# ---------- 3. Caddyfile ----------
if grep -q 'consulting-next' Caddyfile; then
  echo "3. Caddyfile 에 이미 consulting-next 가 있어 건너뜀"
else
  backup Caddyfile
  cat >> Caddyfile <<'EOF'

# 스마트컨설팅 새 앱(FastAPI, 모바일 화면) — 기존 consulting 주소(Streamlit)는 그대로 둔다.
consulting-next.{$BASE_HOST} {
        reverse_proxy consulting-next:8000
}
EOF
  echo "3. Caddyfile 수정 완료"
fi

# ---------- 4. update.sh ----------
if grep -q 'consulting-next' update.sh; then
  echo "4. update.sh 에 이미 consulting-next 가 있어 건너뜀"
else
  backup update.sh
  new_update=$(mktemp "$DEPLOY/update.sh.new.XXXX")
  python3 - "$new_update" <<'EOF'
import sys
text = open("update.sh", encoding="utf-8").read()
anchor = '    [ "$app" != testfarm ] || docker compose up -d --build testfarm-next\n'
assert text.count(anchor) == 1, "update.sh 에서 testfarm-next 줄을 못 찾았습니다"
add = ('    # 스마트컨설팅도 같은 저장소로 새 앱(consulting-next)을 함께 만든다\n'
       '    [ "$app" != consulting ] || docker compose up -d --build consulting-next\n')
open(sys.argv[1], "w", encoding="utf-8").write(text.replace(anchor, anchor + add))
EOF
  # 새 파일이 비어 있지 않고 문법이 맞을 때만 바꾼다 (돌고 있는 update.sh 를 반쯤 쓴 상태로 두지 않으려고 mv 로 한 번에 교체)
  [ -s "$new_update" ] && bash -n "$new_update"
  chmod --reference=update.sh "$new_update"
  mv "$new_update" update.sh
  echo "4. update.sh 수정 완료"
fi

# ---------- 5. 확인·시작 ----------
docker compose config -q && echo "5. docker-compose.yml 문법 확인 통과"
bash -n update.sh && echo "   update.sh 문법 확인 통과"
docker compose up -d --build consulting-next
docker compose up -d caddy
docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile
echo
echo "상태:"
docker compose ps consulting-next
echo
echo "잠시 뒤 확인:  docker logs --tail 30 deploy-consulting-next-1"
echo "주소: https://consulting-next.<BASE_HOST>/  (BASE_HOST 는 $DEPLOY/.env 에 있음)"
