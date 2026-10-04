"""force push를 차단하는 Claude Code PreToolUse 훅.

2026-09-24 이 저장소의 origin/main이 force push로 통째로 교체되어 배포 저장소의
96커밋이 사라진 일이 있었다. 일반 push는 허용하되 force만 막기 위해 둔다.

.claude/settings.json 의 permissions.deny 규칙만으로는 부족하다. 그 규칙은 명령
앞부분만 보기 때문에 `git push origin main --force` 처럼 플래그가 뒤에 오면
빠져나간다. 이 훅은 위치와 무관하게 잡아낸다.

훅 입력(JSON)은 stdin으로 들어온다. 차단할 때만 deny 판정을 stdout에 낸다.
(jq 대신 python을 쓰는 이유: 이 PC에 jq가 설치되어 있지 않았다)

force push가 정말 필요하면 Claude를 거치지 말고 터미널에서 직접 실행할 것.
"""
import sys, json, re

try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)  # 입력을 못 읽으면 조용히 통과 (다른 명령까지 막지 않도록)

cmd = (d.get("tool_input") or {}).get("command", "")
if re.search(r'(^|\s)(--force|--force-with-lease|-f)(\s|=|$)', cmd):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "force push는 차단되어 있습니다. 히스토리를 덮어쓸 수 있으므로 성태님이 터미널에서 직접 실행하세요."}}, ensure_ascii=False))
