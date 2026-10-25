# Diagnosing a failure

Match the message, then fix the cause. Every string below is quoted from the source, so grep for it if line numbers have moved.

## The export button is greyed out

`cmt_exporter/panels.py:25`: `column.enabled = data.IsExportAnimation or data.IsExportModel or data.IsGenerateRef`. Nothing to fix — turn on at least one of those three.

The three sections inside the panel are separately gated. `box.enabled = data.ProjectPath != ""` (`panels.py:41/70/91`) — with no valid project path the model/animation/reference sections are inert. Known cosmetic quirk: the material and ArtDef sections sit inside `if data.IsGenerateRef:` (`panels.py:92`), so they only draw when reference generation is on. Pre-existing, not a state you can repair from script — set `IsGenerateRef` if the user needs to reach those controls.

## `项目路径不正确，请确保资产文件夹已生成（启动一次AssetEditor）`

`cmt_exporter/updates.py` `project_path_update`. The path must be a directory that contains `Assets/`, or whose **basename** contains `Assets/` one level down (`scene_helpers.get_real_project_path` accepts both `path` and `path/<projName>`). On rejection the callback **clears `ProjectPath`** and pops the menu, so it never stays wrong.

Cause is almost always "AssetEditor was never run for this project". Run it once; it creates the tree.

## `AttributeError: 'CMT_Exporter_Settings' object has no attribute 'GeoList'`

A settings handle was held across an addon reload. Re-read `bpy.context.scene.CMT.ExporterSettings` after any disable/enable cycle. Not a product defect.

## `网格 [X] 缺少材质: Civ6 模型要求每个网格至少有一个材质`

`cmt_exporter/operations.py` `export_models`. The mesh has an empty material slot or a slot whose material is unset. The whole export returns `{'CANCELLED'}` — Civ6 requires a material per mesh. Assign one; a plain `bpy.data.materials.new(...)` appended to `obj.data.materials` is enough.

Without this check the .NET side dies deeper with `System.ArgumentOutOfRangeException: 索引超出范围。必须为非负值并小于集合大小。参数名: index` from `MetadataWriter.WriteGeoAnimFile`, because an empty `materials` block reaches `mesh.MaterialBindings[...].Name`.

## `模型 [X] 跳过未绑定骨架的网格: Y`

`export_models`. `Y` has no parent armature (`scene_helpers.get_parent_armature` requires `obj.parent.type == 'ARMATURE'`). Non-fatal: the mesh is dropped from that Geo and the rest continues. Parent the mesh to the armature (a plain `obj.parent = arm` assignment is enough) or deselect it.

## `AttributeError: 'NoneType' object has no attribute 'data'` in `mat_poll`

A Geometry slot has `value = None`. Legitimate state — the UI leaves an empty slot when "add mesh" runs with nothing selected. Any code walking `GeoList[i].Geometries` must skip `None`. Also reachable as `'NoneType' object has no attribute 'type'` / `'parent'` in `do_export` if a `None` reaches the object set.

## `RuntimeError: Operator bpy.ops.object.material_slot_remove_unused.poll() failed, context is incorrect`

Calling the native slot-removal operator on a mesh with **zero** material slots makes its `poll()` return `False`. The addon's own two call sites guard with `.poll()` first; third-party or newly written code must do the same.

## `IndexError: bpy_prop_collection[index]: index 0 out of range, size 0`

Two different causes, both from indexing an empty collection:

- An armature with **no bones** (`bpy.data.armatures.new()` then parenting) — `io_export_cn6.py` reads `armature.bones[0]`. Build test rigs with `bpy.ops.object.armature_add(...)`, which ships one bone.
- An empty `ArtdefList` while `IsExportArtdef` is on — panel draw indexed `ArtdefList[0]`. Toggle `IsExportArtdef` off and on to rebuild the list from the templates.

## `System.IO.DirectoryNotFoundException` (or a .NET file error) on export

An output directory is missing. The plugin does **not** create `Geometries/`, `Animations/`, `Assets/`, `Materials/`, `Textures/`, `ArtDefs/` — that is AssetEditor's job. Deliberate behaviour, not a bug to patch.

The **alpha-channel extraction** path fails differently and with a misleading message, because it writes through Blender's image API rather than the .NET exporter:

```
RuntimeError: 错误: 无法写入图像: internal error, see console
错误: 未能将图像 'X_Alpha' 保存至 '.../Assets/X_Alpha.png'
```

`internal error, see console` from `blender_` here almost always means **the parent directory does not exist** — the extracted `<stem>_Alpha.png` goes to the project's **`Assets/` root** (`export_materials` passes `projpath = get_real_project_path(...)` to `extract_alpha_to_file`), and the `.dds`/`.tex` that end up in `Textures/` are written later by the .NET side. Create `Assets/` (run AssetEditor once) and it goes away.

## An animation exports but no bones move in game

An action slot was skipped because its display name resolved to no armature. `read_action_data` reads `bag.slot.name_display` and looks up an object by that name; unmatched, it drops the slot **silently** — the `.fgx` is still written, just with no bone data.

Check the slot name against the armature object's name; the full naming rule, including the `Slot_` prefix stripping, is in [api.md](api.md) § Which skeleton an animation binds to.

## `ValueError: bpy.app.translations.register: translations message cache already contains some data for addon 'CivModelTool'` / edits not taking effect

Both are a reload that did not complete. The reload procedure is in SKILL.md § Before you touch anything — disable, then purge `sys.modules`, then enable, in that order.

The trap worth repeating: a traceback then shows **new** file/line numbers while the old code actually ran, which reads as "the edit didn't help" or sends you chasing a line that isn't executing. Reload first, then judge.

## Ast reference validation

`Ast 引用类型不匹配，导出已中止` is the popup title; each line under it is `Ast [X] 模型引用 [Y] 类型 Z 不被允许 (允许: ...)` or the same for `动画引用 [Z]` (the slot text). Runs only when `IsGenerateRef and IsExportAst`. The allowed lists come from `AllowedClasses.json`.

Related silent behaviour worth knowing when state "resets itself": changing `Ast.Class` clears the Ast's geometry references and re-derives `DSG`; changing `DSG` clears and rebuilds `Animations`. Fill `Class` first, then `DSG`.

## The texture looks wrong in game (alpha ignored, or a map is missing)

Each texture row has a **通道 / Channel** dropdown to the right of the image picker, defaulting to `BaseColor` — the image exported as-is. If the image packs a meaningful **alpha** channel (a cutout/opacity map) and you want it as its own texture, set that row to `Alpha`. It works on **any** slot, not just `Opacity` (22 of the 27 material classes have no `Opacity` slot at all). The alpha is copied straight through — it is **not** inverted.

The rule (channel follows the source socket, and `Opacity`-named slots map to the BSDF `Alpha` input) and the reason the dropdown is deliberately a static enum are in [api.md](api.md) § `CMT_Exporter_PG_Texture.Channel`. Rows the slot-generation auto-fill does not cover — anything reading a grayscale image through `Color → Alpha`, which it deliberately leaves alone — are filled by `cmt.exporter_ot_automatchtextures`, the **自动匹配贴图** button under the list. `WuwaNormal` only touches rows whose slot name contains `Normal`, and skips rows marked `Alpha` — the two are mutually exclusive.

## The custom texture-export script field silently does nothing

`export_materials` loads the script chosen in **自定义贴图导出脚本** with
`importlib.util.spec_from_file_location` + `exec_module` (`cmt_exporter/operations.py`), but the loaded module is never called afterwards — no hook receives it. So a script that defines a function to customise texture export is loaded and then dropped. This is intentional as far as the current UI goes; if you are wiring a custom script, nothing will happen until the addon is extended to use `customscript`.

The field's suffix guard does work: assigning a path whose extension is not `.py` clears the field and shows a **请选择Python脚本** popup. (It did not until commit `fix: TxtCustomExportScript typo` — the callback read a misspelled attribute, so every write raised `AttributeError` in the console and the bad path was kept. If you see that traceback, you are on an old build.)

## When nothing above matches

`scripts/preflight.py` walks the settings and reports every problem it can see without exporting. Run it first — it is faster than bisecting an export, and it checks the whole tree rather than the one Geo you happened to look at.
