import json
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from crewai import BaseLLM
from .safety import redact


class BudgetLLM(BaseLLM):
    """CrewAI ReAct text adapter with a hard HTTP call budget and no retries."""

    def __init__(self, model, endpoint, key, audit, max_calls=8):
        super().__init__(model=model, temperature=0.2)
        self.endpoint, self.key, self.audit = endpoint, key, audit
        self.max_calls, self.calls = max_calls, 0
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def supports_function_calling(self):
        return False

    def supports_stop_words(self):
        return True

    def get_context_window_size(self):
        return 32000

    def call(
        self, messages, tools=None, callbacks=None, available_functions=None, **kwargs
    ):
        if self.calls >= self.max_calls:
            raise RuntimeError("已达到模型调用上限，停止运行；请查看已保存报告")
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]
        if len(json.dumps(messages, ensure_ascii=False)) > 85000:
            raise RuntimeError("上下文过长，请减少文件数量")
        self.calls += 1
        self.audit("model_request", {"call": self.calls, "messages": messages})
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 2400,
            "stream": False,
            "stop": list(dict.fromkeys([*self.stop_sequences, "Observation:"])),
        }
        if "dashscope.aliyuncs.com" in self.endpoint:
            body["enable_thinking"] = False
        request = Request(
            self.endpoint,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.key,
            },
        )
        started = time.monotonic()
        try:
            with urlopen(request, timeout=90) as response:
                data = json.loads(response.read(2000000))
        except HTTPError as error:
            raise RuntimeError(f"模型接口返回HTTP {error.code}；未自动重试") from None
        except Exception:
            raise RuntimeError("模型网络或响应异常；未自动重试") from None
        content = data["choices"][0]["message"].get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("模型返回空文本")
        for key in self.usage:
            self.usage[key] += int(data.get("usage", {}).get(key, 0))
        self.audit(
            "model_response",
            {
                "call": self.calls,
                "seconds": round(time.monotonic() - started, 2),
                "usage": data.get("usage", {}),
                "text": redact(content),
                "finish_reason": data["choices"][0].get("finish_reason"),
            },
        )
        if data["choices"][0].get("finish_reason") == "length":
            raise RuntimeError("模型输出被截断，报告未标记为完成")
        return content.split("Observation:", 1)[0]
