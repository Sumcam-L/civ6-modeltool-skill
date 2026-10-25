"""Check a scene against Civ6 export requirements before running the export.

Runs inside Blender (``blender -b -P preflight.py`` or via the viewport backend),
because the settings live on the scene. Touches nothing — it only reads.

    blender -b -P preflight.py -- --out report.json

Prints one line ``PREFLIGHT {json}``; exit code 1 if any check is an error.
"""

import json
import os
import sys
from pathlib import Path

import bpy

PROJECT_SUBDIRS = {
    "IsExportModel": ["Geometries"],
    "IsExportAnimation": ["Animations"],
    "IsGenerateRef": ["Assets"],
    # Assets/ also hosts the intermediate <stem>_Alpha.png written by the alpha
    # channel extraction, so a material export needs it even without IsGenerateRef.
    "IsExportMaterial": ["Materials", "Textures", "Assets"],
    "IsExportArtdef": ["ArtDefs"],
}


class Report:
    def __init__(self):
        self.items = []

    def add(self, severity, check, message):
        self.items.append({"severity": severity, "check": check, "message": message})

    def error(self, check, message):
        self.add("error", check, message)

    def warn(self, check, message):
        self.add("warning", check, message)

    def counts(self):
        errors = sum(1 for i in self.items if i["severity"] == "error")
        return errors, len(self.items) - errors


def addon_dir():
    for name in ("CivModelTool", "Civ6ModelTool"):
        module = sys.modules.get(name)
        if module is not None and getattr(module, "__file__", None):
            return Path(module.__file__).parent
    return None


def load_allowed_classes(base):
    if base is None:
        return {}
    path = base / "cmt_exporter" / "assets" / "AllowedClasses.json"
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except OSError:
        return {}


def resolve_project_path(raw):
    """Mirror cmt_exporter.scene_helpers.get_real_project_path."""
    if not raw:
        return None
    path = Path(raw)
    if (path / "Assets").exists():
        return path
    if (path / path.name / "Assets").exists():
        return path / path.name
    return None


def enum_name(group, prop, fallback=""):
    """Read an enum as its identifier string.

    Item access (``group[prop]``) yields the raw index for dynamic enums, so
    attribute access is the only form that gives a usable class name.
    """
    try:
        value = getattr(group, prop)
    except (AttributeError, KeyError, TypeError):
        return fallback
    return str(value) if value else fallback


def check_settings_present(report):
    scene = bpy.context.scene
    if not hasattr(scene, "CMT"):
        report.error("addon", "场景上没有 CMT 属性组：插件未启用。")
        return None, None
    return scene.CMT.ExporterSettings, scene.CMT.S2BSettings


def check_flags(report, data):
    flags = ["IsExportModel", "IsExportAnimation", "IsGenerateRef"]
    if not any(getattr(data, f) for f in flags):
        report.error(
            "flags",
            "IsExportModel / IsExportAnimation / IsGenerateRef 全为 False，导出按钮不可用。",
        )


def check_project_path(report, data):
    raw = data.ProjectPath
    if not raw:
        report.error("project_path", "ProjectPath 为空：先启动一次 Civ6 AssetEditor 生成资产文件夹。")
        return None
    resolved = resolve_project_path(raw)
    if resolved is None:
        report.error(
            "project_path",
            f"ProjectPath [{raw}] 下找不到 Assets/ 目录（需为含 Assets/ 的目录，或其下同名子目录）。",
        )
        return None
    report.add("info", "project_path", f"项目根目录：{resolved}")
    return resolved


def check_output_dirs(report, data, project):
    if project is None:
        return
    for flag, subdirs in PROJECT_SUBDIRS.items():
        if not getattr(data, flag):
            continue
        for subdir in subdirs:
            if not (project / subdir).is_dir():
                report.error(
                    "output_dir",
                    f"{flag} 已开启但缺少输出目录 {project / subdir}（插件不会自建，需由 AssetEditor 创建）。",
                )


def iter_geo_slots(data):
    for geo in data.GeoList:
        for index, slot in enumerate(geo.Geometries):
            yield geo, index, slot.value


def check_geometries(report, data):
    if not data.IsExportModel:
        return
    names = {}
    for geo in data.GeoList:
        names.setdefault(geo.FileName, 0)
        names[geo.FileName] += 1

    for name, count in names.items():
        if not name:
            report.error("geometry", "存在 FileName 为空的模型条目。")
        elif count > 1:
            report.error("geometry", f"模型文件名重复 {count} 次：{name}（导出会互相覆盖）。")

    for geo in data.GeoList:
        if len(geo.Geometries) == 0:
            report.error("geometry", f"模型 [{geo.FileName}] 没有任何网格槽位，导出不会产出文件。")
            continue

        usable = 0
        for index, slot in enumerate(geo.Geometries):
            obj = slot.value
            if obj is None:
                report.warn(
                    "geometry",
                    f"模型 [{geo.FileName}] 槽位 {index} 为空（未指定网格），导出时会被跳过。",
                )
                continue
            if obj.type != "MESH":
                report.error(
                    "geometry",
                    f"模型 [{geo.FileName}] 槽位 {index} 指向非网格对象 [{obj.name}]（{obj.type}）。",
                )
                continue
            usable += 1

            if obj.parent is None or obj.parent.type != "ARMATURE":
                report.error(
                    "geometry",
                    f"网格 [{obj.name}] 没有父级骨架，导出时会被跳过（模型 [{geo.FileName}]）。",
                )

            slots = obj.material_slots
            if len(slots) == 0:
                report.error(
                    "geometry",
                    f"网格 [{obj.name}] 没有材质槽，Civ6 要求每个网格至少一个材质，导出会中止。",
                )
            else:
                empty = [i for i, s in enumerate(slots) if s.material is None]
                if empty:
                    report.error(
                        "geometry",
                        f"网格 [{obj.name}] 的材质槽 {empty} 为空，导出会中止。",
                    )

            if len(obj.data.uv_layers) == 0:
                report.error(
                    "geometry",
                    f"网格 [{obj.name}] 没有 UV 层，写 .fgx 时会 IndexError。",
                )

            bones = len(obj.parent.data.bones) if obj.parent and obj.parent.type == "ARMATURE" else 0
            if bones and geo.Class in ("Unit", "Leader"):
                limit = 60 if geo.Class == "Unit" else 256
                if bones > limit:
                    report.warn(
                        "geometry",
                        f"骨架 [{obj.parent.name}] 有 {bones} 根骨骼，超过 {geo.Class} 的 {limit} 上限"
                        "（游戏侧限制，插件不拦截）。",
                    )

        if usable == 0:
            report.error("geometry", f"模型 [{geo.FileName}] 没有可用网格，导出不会产出文件。")


def check_ast_references(report, data, allowed):
    if not (data.IsGenerateRef and data.IsExportAst):
        return
    geo_class = {g.FileName: enum_name(g, "Class") for g in data.GeoList}
    anm_class = {}
    for entry in data.AnimationList:
        if entry.value is not None:
            anm_class[entry.value.name] = enum_name(entry, "Class")

    for ast in data.AstList:
        ast_class = enum_name(ast, "Class")
        rules = allowed.get(ast_class, {})
        allowed_geo = rules.get("geo", [])
        allowed_anm = rules.get("anm", [])

        if not ast_class:
            report.error("ast", f"Ast [{ast.FileName}] 未设置类型。")
            continue

        for ref in ast.Geometries:
            name = ref.value
            if not name:
                report.warn("ast", f"Ast [{ast.FileName}] 有一条空的模型引用。")
                continue
            if name not in geo_class:
                report.error("ast", f"Ast [{ast.FileName}] 引用的模型 [{name}] 不在模型列表中。")
                continue
            klass = geo_class[name]
            if klass and klass not in allowed_geo:
                report.error(
                    "ast",
                    f"Ast [{ast.FileName}] 模型引用 [{name}] 类型 {klass} 不被允许"
                    f"（允许: {', '.join(allowed_geo) or '无'}）。",
                )

        empty = set()
        for slot in ast.Animations:
            if slot.value is None and slot.text:
                empty.add(slot.text)
        if empty:
            names = sorted(empty)
            shown = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
            report.warn(
                "ast",
                f"Ast [{ast.FileName}] 有 {len(names)} 个动画槽位未指定动作：{shown}",
            )

        for slot in ast.Animations:
            action = slot.value
            if action is None:
                continue
            klass = anm_class.get(action.name)
            if klass is None:
                report.error(
                    "ast",
                    f"Ast [{ast.FileName}] 动画槽位 [{slot.text}] 使用的动作 [{action.name}]"
                    " 不在动画导出列表中。",
                )
            elif klass not in allowed_anm:
                report.error(
                    "ast",
                    f"Ast [{ast.FileName}] 动画引用 [{slot.text}] 类型 {klass} 不被允许"
                    f"（允许: {', '.join(allowed_anm) or '无'}）。",
                )


def _action_is_empty(action):
    """动作里完全没有任何动画数据（fcurves 与 layered channelbags 皆空）时返回 True。"""
    if len(action.fcurves) > 0:
        return False
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            if len(getattr(strip, "channelbags", [])) > 0:
                return False
    return True


def check_animations(report, data):
    if not data.IsExportAnimation:
        return
    for index, entry in enumerate(data.AnimationList):
        if entry.value is None:
            report.error("animation", f"动画条目 {index} 未指定动作，导出会中止。")
            continue
        if _action_is_empty(entry.value):
            report.warn("animation", f"动作 [{entry.value.name}] 没有关键帧。")
    if len(data.AnimationList) == 0:
        report.warn("animation", "IsExportAnimation 已开启但动画列表为空。")


def _image_of_channel(material, image_name, channel):
    """Return the image datablock a texture row will actually read, or None.

    Mirrors what export_materials does: it resolves the row's image to an
    on-disk path, so the row is dead when the material has no such TEX_IMAGE.
    For the Alpha channel the extraction additionally needs the source file to
    carry an alpha channel, which we cannot know without opening the file, so we
    only report the clearly-wrong case here.
    """
    node = material.node_tree.nodes if material.use_nodes and material.node_tree else None
    if not node:
        return None
    for tex in (n for n in node if n.type == "TEX_IMAGE"):
        if tex.image is not None and tex.image.name == image_name:
            return tex.image
    return None


def check_artdefs(report, data):
    if not data.IsExportArtdef:
        return
    if len(data.ArtdefList) == 0:
        report.error(
            "artdef",
            "IsExportArtdef 已开启但 ArtdefList 为空：面板会 IndexError，"
            "取消勾选后再勾选可重建列表。",
        )
        return
    for index, artdef in enumerate(data.ArtdefList):
        for inst in artdef.Instances:
            if not inst.Type:
                report.warn("artdef", f"Artdef 条目 {index} 有一条未填写 Type 的引用。")


def check_materials(report, data):
    if not data.IsExportMaterial:
        return
    for mat in data.MaterialList:
        if mat.FileName not in bpy.data.materials:
            report.error("material", f"材质列表中的 [{mat.FileName}] 在场景里已不存在。")
            continue
        used = [t.text for t in mat.Textures if t.value not in ("", "None")]
        if not used:
            report.warn("material", f"材质 [{mat.FileName}] 没有匹配到任何贴图，导出只有非贴图属性。")
        for tex in mat.Textures:
            if tex.Channel != "Alpha" or tex.value in ("", "None"):
                continue
            channel = getattr(tex, "Channel", "BaseColor")
            image = _image_of_channel(bpy.data.materials[mat.FileName], tex.value, channel)
            if image is None:
                report.warn(
                    "material",
                    f"材质 [{mat.FileName}] 的槽位 [{tex.text}] 标成了 Alpha，但贴图 [{tex.value}] "
                    f"取不到对应通道，导出时会跳过这次提取。",
                )
    script = data.TexCustomExportScript
    if script and Path(script).suffix != ".py":
        report.warn(
            "material",
            f"自定义贴图导出脚本 [{script}] 不是 .py 文件（正常应在选中时就被清空，"
            f"多半来自旧版本或另存的文件）。",
        )


def check_shapekey(scene, report):
    settings = scene.CMT.S2BSettings
    mesh = settings.TargetMesh
    if mesh is None:
        return
    if mesh.type != "MESH":
        report.error("shapekey", f"目标网格 [{mesh.name}] 不是网格对象。")
        return
    if mesh.data.shape_keys is None:
        report.warn("shapekey", f"目标网格 [{mesh.name}] 没有形态键，转换不会产生任何骨骼。")
    armature = settings.CurrentArmature
    if armature is not None and len(armature.data.bones) == 0:
        report.error("shapekey", f"目标骨架 [{armature.name}] 没有骨骼，写入会崩溃。")


def main():
    report = Report()
    data, _ = check_settings_present(report)
    if data is None:
        return emit(report)

    base = addon_dir()
    if base is None:
        report.warn("addon", "找不到已加载的 CivModelTool 模块，跳过类型表校验。")
    allowed = load_allowed_classes(base)

    check_flags(report, data)
    project = check_project_path(report, data)
    check_output_dirs(report, data, project)
    check_geometries(report, data)
    check_ast_references(report, data, allowed)
    check_animations(report, data)
    check_materials(report, data)
    check_artdefs(report, data)
    check_shapekey(bpy.context.scene, report)
    return emit(report)


def emit(report):
    """Print the report and return the error count (so ``main`` can set the exit code)."""
    errors, warnings = report.counts()
    payload = {
        "ok": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "items": report.items,
    }
    out = None
    argv = sys.argv
    if "--" in argv:
        rest = argv[argv.index("--") + 1:]
        if "--out" in rest:
            out = rest[rest.index("--out") + 1]
    if out:
        with open(out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    print("PREFLIGHT " + json.dumps(payload, ensure_ascii=False))
    return errors


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
