"""요청 본문 크기 제한 — 큰 파일을 올려 서버 메모리(컨테이너 500MB)를 채우는 것을 막는다.

본문을 다 읽은 뒤가 아니라 Content-Length 로 먼저 거절하고, 길이를 속이거나 청크로 보내도 읽는 도중에 한도를 넘으면 끊는다.
한도: 백업 복원 50MB, 파일 업로드(multipart: 엑셀 일괄 등록 등) 12MB, 그 밖의 JSON 요청 2MB.
"""
import json

RESTORE_LIMIT = 50 * 1024 * 1024
UPLOAD_LIMIT = 12 * 1024 * 1024          # 엑셀 한도(10MB) + 양식 필드 여유
JSON_LIMIT = 2 * 1024 * 1024


def limit_for(path: str, content_type: str) -> int:
    if path.endswith("/backup/restore"):
        return RESTORE_LIMIT
    if content_type.startswith("multipart/form-data"):
        return UPLOAD_LIMIT
    return JSON_LIMIT


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        limit = limit_for(scope["path"], headers.get("content-type", ""))
        declared = headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            return await self._reject(send, limit)

        seen = 0
        exceeded = False
        replaced = False

        async def counting_receive():
            nonlocal seen, exceeded
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    # 예외를 던지면 FastAPI 가 본문 해석 오류(400)로 바꿔 버린다. 읽기를 여기서 끝내고, 앱이 무슨 답을 하든 아래에서 413 으로 바꾼다.
                    exceeded = True
                    return {"type": "http.request", "body": b"", "more_body": False}
            return message

        async def replacing_send(message):
            nonlocal replaced
            if not exceeded:
                return await send(message)
            if not replaced:
                replaced = True
                await self._reject(send, limit)          # 앱의 답은 버리고 413 하나만 보낸다

        await self.app(scope, counting_receive, replacing_send)

    @staticmethod
    async def _reject(send, limit):
        body = json.dumps({"detail": f"보낸 내용이 너무 큽니다 (최대 {limit // (1024 * 1024)}MB)."}, ensure_ascii=False).encode("utf-8")
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json; charset=utf-8"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
