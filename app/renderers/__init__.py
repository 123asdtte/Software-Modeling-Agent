"""渲染器层：领域模型 → PlantUML 源码 → PNG 图片。

当前状态：占位边界。计划实现 render_usecase_plantuml() 等纯函数渲染器
（模型 → PlantUML 源码），PlantUML 本地 jar 负责源码 → PNG（可降级返回源码）。
禁止让 LLM 直接输出 PlantUML（评审 P0 约束：LLM 只产结构化 JSON）。
"""
