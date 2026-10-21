import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .service import AIService
from .provider import ProviderError
from .asr import AliyunASR


def make_handler(service, asr_factory=AliyunASR):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body):
            raw = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == "/health":
                self.reply(200, {"data": {"status": "ok", "mode": service.mode}})
            else:
                self.reply(404, {"error": "接口不存在"})

        def do_POST(self):
            routes = {"/api/ai/evaluations": service.evaluate,
                      "/api/ai/suggestions": service.suggest,
                      "/api/ai/comparisons": service.compare,
                      "/api/ai/transcriptions": lambda data: asr_factory().submit(data),
                      "/api/ai/transcriptions/query": lambda data: asr_factory().fetch(data)}
            if self.path not in routes:
                self.reply(404, {"error": "接口不存在"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 1_000_000:
                    self.reply(413, {"error": "请求超过1MB"})
                    return
                if length <= 0:
                    raise ValueError("请求体不能为空")
                self.connection.settimeout(15)
                data = json.loads(self.rfile.read(length))
                self.reply(200, {"data": routes[self.path](data)})
            except (ValueError, UnicodeError) as exc:
                self.reply(400, {"error": str(exc)})
            except ProviderError as exc:
                self.reply(502, {"error": str(exc)})
            except TimeoutError:
                self.reply(408, {"error": "读取请求超时"})
            except Exception:
                logging.error("AI request failed; payload omitted")
                self.reply(500, {"error": "内部处理错误"})
    return Handler


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8010), make_handler(AIService()))
    print("爱教学AI服务：http://127.0.0.1:8010")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
