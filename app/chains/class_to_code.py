"""类图 → Java 代码骨架（确定性模板生成，不调用 LLM、不耗 token）。

设计约束：
- 相同 ClassModel 输入 → 完全相同输出（可单测断言）；
- 只生成可编译的骨架：未知/空类型回退 Object、空返回类型回退 void；
- 具体方法的 TODO 用 ``throw new UnsupportedOperationException`` 占位，
  保证任意返回类型都能通过 Java 编译；
- 继承/实现关系映射到 extends/implements；组合/聚合映射为成员字段；
- 不做业务逻辑推断，不引入第三方依赖。
"""

import re

from app.models.uml import ClassItem, ClassModel, ClassRelationType

# Java 保留字（标识符冲突时追加下划线）
_JAVA_KEYWORDS = frozenset(
    {
        "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
        "class", "const", "continue", "default", "do", "double", "else", "enum",
        "extends", "final", "finally", "float", "for", "goto", "if", "implements",
        "import", "instanceof", "int", "interface", "long", "native", "new",
        "package", "private", "protected", "public", "return", "short", "static",
        "strictfp", "super", "switch", "synchronized", "this", "throw", "throws",
        "transient", "try", "void", "volatile", "while", "true", "false", "null",
        "var", "record", "sealed", "permits",
    }
)

# 常见中文类型 → Java 类型（LLM 偶尔输出中文类型名，做一次温和归一）
_TYPE_MAP = {
    "字符串": "String",
    "文本": "String",
    "整数": "int",
    "长整数": "long",
    "小数": "double",
    "浮点数": "double",
    "布尔": "boolean",
    "布尔值": "boolean",
    "日期": "java.time.LocalDate",
    "时间": "java.time.LocalDateTime",
    "列表": "java.util.List",
    "集合": "java.util.List",
}

_VISIBILITY = {"+": "public", "-": "private", "#": "protected", "~": ""}


def _java_ident(name: str, fallback: str = "value") -> str:
    """把任意名称归一为合法 Java 标识符（保留 Unicode 字母，中文类名可编译）。"""
    candidate = re.sub(r"[^\w$]", "_", (name or "").strip(), flags=re.UNICODE)
    if not candidate:
        candidate = fallback
    if candidate[0].isdigit():
        candidate = f"{fallback}_{candidate}"
    if candidate in _JAVA_KEYWORDS:
        candidate += "_"
    return candidate


def _java_type(type_name: str, default: str = "Object") -> str:
    """空类型回退默认值；常见中文类型做一次映射。"""
    text = (type_name or "").strip()
    if not text:
        return default
    return _TYPE_MAP.get(text, text)


def _lower_camel(name: str) -> str:
    ident = _java_ident(name, "ref")
    return ident[0].lower() + ident[1:]


def _visibility(visibility, default: str) -> str:
    """UML 可见性 → Java 修饰符；缺省用 default。"""
    if visibility is None:
        return default
    return _VISIBILITY.get(visibility.value, default)


def _header(item: ClassItem, model: ClassModel) -> str:
    """生成类型声明头：extends/implements 由泛化/实现关系推导。

    - 类：generalization → extends（Java 单继承，取第一条）；
      realization → implements（可多条）；
    - 接口：两者统一为 extends（接口可多继承接口）。
    """
    generalizes: list[str] = []
    realizes: list[str] = []
    for rel in model.relations:
        if rel.source_id != item.name:
            continue
        if rel.type == ClassRelationType.GENERALIZATION:
            generalizes.append(_java_ident(rel.target_id, "Type"))
        elif rel.type == ClassRelationType.REALIZATION:
            realizes.append(_java_ident(rel.target_id, "Type"))

    if item.is_interface:
        supers = generalizes + realizes
        suffix = f" extends {', '.join(supers)}" if supers else ""
        return f"public interface {_java_ident(item.name, 'Type')}{suffix} {{"

    prefix = "public abstract class" if item.is_abstract else "public class"
    suffix = f" extends {generalizes[0]}" if generalizes else ""
    if realizes:
        suffix += f" implements {', '.join(realizes)}"
    return f"{prefix} {_java_ident(item.name, 'Type')}{suffix} {{"


def _field_lines(item: ClassItem, model: ClassModel) -> list[str]:
    """属性字段 + 组合/聚合推导出的成员字段（去重，保持确定性顺序）。"""
    if item.is_interface:
        return []

    lines: list[str] = []
    seen_types: set[str] = set()
    seen_names: set[str] = set()

    for attr in item.attributes:
        field_type = _java_type(attr.type)
        field_name = _java_ident(attr.name, "field")
        if field_name in seen_names:
            continue
        seen_names.add(field_name)
        seen_types.add(field_type)
        mods = "static " if attr.is_static else ""
        vis = _visibility(attr.visibility, "private")
        prefix = f"{vis} " if vis else ""
        lines.append(f"    {prefix}{mods}{field_type} {field_name};")

    # 组合/聚合：整体持有部分（强/弱拥有），补一个成员字段
    for rel in model.relations:
        if rel.source_id != item.name:
            continue
        if rel.type not in (ClassRelationType.COMPOSITION, ClassRelationType.AGGREGATION):
            continue
        field_type = _java_ident(rel.target_id, "Type")
        field_name = _lower_camel(rel.target_id)
        if field_type in seen_types or field_name in seen_names:
            continue
        seen_types.add(field_type)
        seen_names.add(field_name)
        lines.append(f"    private {field_type} {field_name};")

    return lines


def _method_lines(item: ClassItem) -> list[str]:
    """方法：接口/抽象方法输出声明，具体方法输出可编译骨架。"""
    lines: list[str] = []
    for method in item.methods:
        method_name = _java_ident(method.name, "method")
        return_type = _java_type(method.return_type, "void")
        params = ", ".join(
            f"{_java_type(p.type)} {_java_ident(p.name, 'arg')}" for p in method.params
        )
        vis = _visibility(method.visibility, "public")
        mods: list[str] = []
        if vis:
            mods.append(vis)
        if method.is_static:
            mods.append("static")
        is_abstract_member = method.is_abstract and (item.is_abstract or item.is_interface)
        if is_abstract_member:
            mods.append("abstract")
        signature = f"    {' '.join(mods)} {return_type} {method_name}({params})"

        if item.is_interface or is_abstract_member:
            lines.append(f"{signature};")
            continue

        lines.append(f"{signature} {{")
        lines.append("        // TODO: 实现业务逻辑")
        if return_type != "void":
            lines.append('        throw new UnsupportedOperationException("TODO");')
        lines.append("    }")
    return lines


def _render_class(item: ClassItem, model: ClassModel) -> str:
    body = _field_lines(item, model) + _method_lines(item)
    lines = ["// 由 AI 教学智能体平台根据类图模型自动生成（骨架代码）"]
    lines.append(_header(item, model))
    lines.extend(body)
    lines.append("}")
    return "\n".join(lines) + "\n"


def class_model_to_java(model: ClassModel, package: str = "com.example") -> dict[str, str]:
    """把类图模型转换为 Java 源文件字典（文件名 → 源码）。

    Args:
        model: 已通过校验的 ClassModel。
        package: Java 包名；空字符串表示不输出 package 声明。

    Returns:
        ``{"Student.java": "<源码>", ...}``，顺序与 model.classes 一致。

    Raises:
        TypeError: 传入非 ClassModel。
    """
    if not isinstance(model, ClassModel):
        raise TypeError(f"class_model_to_java 只接受 ClassModel，收到 {type(model).__name__}")

    package_line = f"package {package};\n\n" if package else ""
    files: dict[str, str] = {}
    for item in model.classes:
        file_name = f"{_java_ident(item.name, 'Type')}.java"
        source = package_line + _render_class(item, model)
        files[file_name] = source
    return files
