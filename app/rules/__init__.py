"""分图质检规则引擎（纯代码，不调用 LLM，不耗 token）。

当前状态：占位边界。计划按 `docs/03-技术方案/04_UML建模Agent详细技术方案.md`
实现用例图 9 条 / 活动图 10 条 / 状态机图 11 条校验规则，输入
app/models/uml.py 的领域模型，输出 app/models/review.py 的 ReviewReport。
"""
