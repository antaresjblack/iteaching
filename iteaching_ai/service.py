import math
import os
from datetime import date
from uuid import uuid4
from .provider import ModelProvider, ProviderError
from .config import load_env

from .rubric import VERSION as RUBRIC_VERSION, CRITERIA, RULES
RUBRIC = {
    "bridge_in": "导入：联系主题、激发思考",
    "objectives": "学习目标：清晰说明预期学习成果",
    "pre_assessment": "前测：了解已有知识基础",
    "participatory_learning": "参与式学习：提供讨论、练习等机会",
    "post_assessment": "后测：检查目标达成情况",
    "summary": "总结：归纳重点与反馈",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def text(value):
    return isinstance(value, str) and bool(value.strip())


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_input(data):
    require(isinstance(data, dict), "请求必须是对象")
    for field in ("course_id", "lesson_id", "taught_at"):
        require(text(data.get(field)), field + "不能为空")
    date.fromisoformat(data["taught_at"])
    require(isinstance(data.get("teaching_goals", ""), str), "teaching_goals必须是文本")
    require(len(data.get("teaching_goals", "")) <= 10000, "教学目标过长")
    segments = data.get("segments")
    require(isinstance(segments, list) and 1 <= len(segments) <= 5000, "需提供1至5000个文本片段")
    ids = set()
    total = 0
    previous_start = -1
    for s in segments:
        require(isinstance(s, dict), "片段必须是对象")
        require(text(s.get("id")) and s["id"] not in ids, "片段ID不能为空或重复")
        ids.add(s["id"])
        require(text(s.get("text")), "片段文本不能为空")
        total += len(s["text"])
        start, end = s.get("start_seconds"), s.get("end_seconds")
        require(number(start) and number(end) and 0 <= start < end, "片段时间范围不合法")
        require(start >= previous_start, "片段需按开始时间排序")
        previous_start = start
    require(total <= 50000, "课堂文本超出50000字符限制，请拆分课堂资料")


def validate_indicators(items, segments=None):
    require(isinstance(items, list) and len(items) == len(RUBRIC), "必须包含完整六项评价")
    seen = set()
    for item in items:
        require(isinstance(item, dict), "指标必须是对象")
        key = item.get("id")
        require(isinstance(key, str) and key in RUBRIC and key not in seen, "指标ID无效或重复")
        seen.add(key)
        require(text(item.get("reason")), "评价说明不能为空")
        status, score = item.get("status"), item.get("score")
        evidence = item.get("evidence")
        require(isinstance(evidence, list), "evidence必须是列表")
        require(status in ("evaluated", "insufficient_evidence"), "评价状态无效")
        if status == "insufficient_evidence":
            require(score is None and not evidence, "依据不足项不能含得分或证据")
        else:
            require(number(score) and 0 <= score <= 100 and bool(evidence), "已评价项需有效得分及证据")
        problems = item.get("problems", [])
        require(isinstance(problems, list) and len(problems) <= 10, "问题列表无效")
        for problem in problems:
            require(status == "evaluated" and isinstance(problem, dict), "问题必须属于已观察维度")
            require(text(problem.get("description")) and len(problem["description"]) <= 1800, "问题描述无效")
            references = problem.get("evidence")
            require(isinstance(references, list) and bool(references), "问题必须有原文证据")
            for reference in references:
                require(isinstance(reference, dict) and text(reference.get("segment_id")) and text(reference.get("quote")), "问题证据无效")
                if segments is not None:
                    require(reference["segment_id"] in segments and reference["quote"] in segments[reference["segment_id"]], "问题引用了不存在的原文证据")
        for e in evidence:
            require(isinstance(e, dict) and text(e.get("segment_id")) and text(e.get("quote")), "证据结构无效")
            if segments is not None:
                require(e["segment_id"] in segments and e["quote"] in segments[e["segment_id"]], "评价引用了不存在的原文证据")


def validate_evaluation(e):
    require(isinstance(e, dict), "evaluation必须是完整评价对象")
    for field in ("evaluation_id", "course_id", "lesson_id", "taught_at", "rubric_version", "summary"):
        require(text(e.get(field)), field + "不能为空")
    date.fromisoformat(e["taught_at"])
    require(type(e.get("demo")) is bool, "demo必须是布尔值")
    require(e["rubric_version"] in ("boppps-text-v1", "boppps-text-v2", RUBRIC_VERSION), "不支持此指标版本")
    validate_indicators(e.get("indicators"))
    if e["demo"]:
        require(all(i["score"] is None for i in e["indicators"]), "演示评价不能包含得分")


class AIService:
    def __init__(self, provider=None, mode=None):
        load_env()
        self.mode = mode or ("live" if provider is not None else os.getenv("ITEACHING_MODE", "demo"))
        require(self.mode in ("live", "demo"), "运行模式必须为live或demo")
        self.provider = provider or (ModelProvider() if self.mode == "live" else None)

    def evaluate(self, data):
        validate_input(data)
        if self.mode == "demo":
            result = {"summary": "演示模式：已接收课堂文本，尚未执行真实AI评价。", "indicators": [
                {"id": key, "status": "insufficient_evidence", "score": None,
                 "reason": "演示模式未调用模型，待真实分析及人工复核。", "evidence": []}
                for key in RUBRIC
            ]}
        else:
            payload = {"rubric": RUBRIC, "criteria": CRITERIA, "scoring_rules": RULES, "segments": data["segments"], "teaching_goals": data.get("teaching_goals", "")}
            source = {s["id"]: s["text"] for s in data["segments"]}
            for attempt in range(1, 4):
                result = self.provider.generate("evaluate", payload)
                try:
                    require(isinstance(result, dict) and text(result.get("summary")), "缺少评价摘要")
                    validate_indicators(result.get("indicators"), source)
                    break
                except ValueError as exc:
                    reason = str(exc)
                    retryable = reason in ("评价引用了不存在的原文证据", "问题引用了不存在的原文证据")
                    if not retryable:
                        raise ProviderError("模型评价校验失败：" + reason) from None
                    if attempt == 3:
                        raise ProviderError("模型评价连续3次生成仍未通过原文证据校验：" + reason) from None
                    print(f"Worker：评价第{attempt}次原文证据校验失败，重新生成（最多3次）", flush=True)
                    payload = {**payload, "validation_feedback": {
                        "error": reason,
                        "instruction": "重新生成完整评价。逐一核对所有evidence：segment_id必须来自输入，quote必须是对应片段text中连续、逐字一致的原文子串。不得纠正转写用词、改写、拼接不同片段或添加省略号；评价证据和问题证据均需核对。仅复制与判断相关且可核实的短引文，不得通过捏造或强行全部置空规避校验。",
                        "attempt": attempt + 1,
                    }}
        return {"evaluation_id": str(uuid4()), "course_id": data["course_id"],
                "lesson_id": data["lesson_id"], "taught_at": data["taught_at"],
                "rubric_version": RUBRIC_VERSION, "demo": self.mode == "demo",
                "summary": result["summary"], "indicators": result["indicators"]}

    def suggest(self, data):
        require(isinstance(data, dict), "请求必须是对象")
        e = data.get("evaluation")
        validate_evaluation(e)
        require(e["demo"] == (self.mode == "demo"), "评价模式与服务模式不一致")
        supported = {i["id"] for i in e["indicators"] if i["status"] == "evaluated"}
        gaps = [{"indicator_id": i["id"], "action": "补充该环节的课堂文本或相关材料，再进行复核。"}
                for i in e["indicators"] if i["status"] == "insufficient_evidence"]
        suggestions = []
        rejected = 0
        if self.mode == "live" and supported:
            result = self.provider.generate("suggest", {"evaluation": {**e, "indicators": [i for i in e["indicators"] if i["id"] in supported]}, "allowed_indicator_ids": sorted(supported)})
            try:
                require(isinstance(result, dict), "建议结果必须是对象")
                suggestions = result.get("suggestions")
                require(isinstance(suggestions, list) and len(suggestions) <= 12, "建议列表无效")
                accepted = []
                for s in suggestions:
                    require(isinstance(s, dict), "建议必须是对象")
                    require(text(s.get("indicator_id")) and s["indicator_id"] in RUBRIC, "建议指标ID无效")
                    if s["indicator_id"] not in supported:
                        rejected += 1
                        continue
                    require(s.get("priority") in ("high", "medium", "low"), "建议优先级无效")
                    require(all(text(s.get(k)) for k in ("problem", "action", "verification")), "建议内容不完整")
                    accepted.append(s)
                suggestions = accepted
            except ValueError as exc:
                raise ProviderError("模型建议校验失败：" + str(exc)) from None
        return {"evaluation_id": e["evaluation_id"], "demo": e["demo"], "suggestions": suggestions, "evidence_gaps": gaps, "status": "partial" if rejected else "complete",
                "warnings": [f"已拦截{rejected}条关联依据不足维度的建议；未将其视为教学缺陷。"] if rejected else []}

    def compare(self, data):
        require(isinstance(data, dict), "请求必须是对象")
        evaluations = data.get("evaluations")
        require(isinstance(evaluations, list) and 2 <= len(evaluations) <= 20, "需要2至20次课堂评价")
        for e in evaluations:
            validate_evaluation(e)
        for field in ("course_id", "rubric_version", "demo"):
            require(len({e[field] for e in evaluations}) == 1, "历史评价的" + field + "必须一致")
        require(len({e["lesson_id"] for e in evaluations}) == len(evaluations), "不能重复比较同一课次")
        require(len({e["evaluation_id"] for e in evaluations}) == len(evaluations), "评价ID不能重复")
        ordered = sorted(evaluations, key=lambda e: (e["taught_at"], e["lesson_id"]))
        series = []
        persistent = []
        for key in RUBRIC:
            points = []
            for e in ordered:
                item = next(i for i in e["indicators"] if i["id"] == key)
                points.append({"lesson_id": e["lesson_id"], "taught_at": e["taught_at"], "score": item["score"]})
            first, last = points[0]["score"], points[-1]["score"]
            delta = round(last - first, 2) if first is not None and last is not None else None
            trend = "not_comparable" if delta is None else ("improved" if delta > 0 else "declined" if delta < 0 else "stable")
            if all(p["score"] is not None and p["score"] < 60 for p in points[-2:]):
                persistent.append(key)
            series.append({"indicator_id": key, "points": points, "delta": delta, "trend": trend})
        comparable = sum(i["delta"] is not None for i in series)
        return {"course_id": ordered[0]["course_id"], "rubric_version": ordered[0]["rubric_version"],
                "demo": ordered[0]["demo"], "series": series, "persistent_weak_indicators": persistent,
                "summary": f"共比较{len(ordered)}次课堂，{comparable}项指标可进行首末对比；最近两次持续低于60分的指标共{len(persistent)}项。",
                "limitations": "分数变化仅用于辅助观察，不证明改进措施产生因果效果；缺失分数不补零。同日课次按ID排序。"}
