---
name: civ6-modeltool
description: "Drive the Civ6ModelTool Blender addon (CmT / cmt.* operators) to export Civilization VI 3D assets — .fgx models and animations, .ast reference files, textures/materials, and ArtDef XML. Use when a task involves the exporter panel, Civ6 model/animation/ast/artdef export, the shape-key-to-bone converter, cleaning a mesh for export, or diagnosing a Civ6 export failure in Blender."
disable-model-invocation: true
---

# Civ6ModelTool

Blender addon (`D:\blender\Common\scripts\addons\CivModelTool`) that exports Civ6 assets. One Python namespace: **`cmt.*`** — 30 operators. Two settings roots off the scene:

```python
data = bpy.context.scene.CMT.ExporterSettings   # export panel
s2b  = bpy.context.scene.CMT.S2BSettings        # shape-key-to-bone panel
```

Everything is scriptable — the UI and the operators touch the same collections, so writing `data` directly is equivalent to clicking. Prefer that over operators: fewer dialogs, fewer context requirements.

## Pick a branch

### Export something (model / animation / .ast / material / ArtDef)

1. Make sure `data.ProjectPath` points at a real Civ6 project — a directory that contains `Assets/`. It is AssetEditor's job to create that tree (run it once); the addon never creates directories.
2. Run `scripts/preflight.py`. It reads the scene and reports every problem it can see — bone-less armatures, missing UV layers, empty material slots, missing output folders — without exporting.
3. Fill the list the export needs, in `data`. Which list, and the exact field names, are in [reference/api.md](reference/api.md); what a mesh must satisfy before it can be exported is in [reference/model-requirements.md](reference/model-requirements.md).
4. Turn on the flag for the stage you want: `IsExportModel`, `IsExportAnimation`, `IsGenerateRef`, `IsExportMaterial`, `IsExportArtdef`.
5. `bpy.ops.cmt.exporter_ot_export()` — one call runs every enabled stage.
6. **Stat the written files.** A `{'FINISHED'}` is not proof: the .NET side writes the `.fgx`, and a Geo whose mesh slots were all skipped produces no file at all.

### Convert a shape-key animation to bones

`cmt.s2b_ot_convert` — set `s2b.TargetMesh`, `s2b.CurrentArmature`, `s2b.ParentBone`, `s2b.MaxBones` first, then run it. It produces an action named `SKB_<shape key animation>` and one bone per shape key. `cmt.s2b_ot_clearshapekey` then removes the shape-key track (zeroes the keys, keeps `Basis`). Both live in [reference/api.md](reference/api.md) § Operations.

### Tidy a mesh before export

`cmt.ot_ot_removeemptyvertexgroups`, `..._removenotbindinggroups`, `..._removegroupfromvertexs`, `..._removeemptymaterialslots`, `..._removeemptyshapekeys` — all act on the selection, all warn and no-op when nothing is selected. What each one actually deletes is in `wiki/工具面板.md`.

### Something failed, or the export button is greyed out

[reference/troubleshooting.md](reference/troubleshooting.md) is ordered by error string — match the message, then fix the cause. Also the first place to look when the panel looks inert.

### The user is clicking it themselves in the GUI

Point them at the repo's own `wiki/` next to the addon — `导出面板.md`, `工具面板.md`, `型态键转骨.md`, `完整工作流.md`, `插件更新.md`. That is the human manual and it is accurate; don't re-derive panel text from the source.

## Before you touch anything

- **Blender on Windows only.** `cmt_exporter/civ6_data.py` loads four .NET assemblies (`Firaxis.Utility`, `Firaxis.Granny`, `Firaxis.Granny.Impl`, `CivNexus6`) at import time, so importing the package outside Blender raises. Never `pip install` anything to "fix" this.
- **`cmt.updater_run` replaces the entire addon directory** with GitHub `main`, discarding local edits. Never call it against a working copy. `cmt.updater_check` is read-only and safe.
- **Edited source is not live.** Blender keeps running the module objects from enable time, so a traceback then shows new line numbers while old code ran. Reload as `bpy.ops.preferences.addon_disable(module="CivModelTool")` → delete every `CivModelTool*` key from `sys.modules` → `bpy.ops.preferences.addon_enable(module="CivModelTool")`, in that order. Purging before disabling makes the disable a no-op and the next enable fails with `translations message cache already contains some data for addon 'CivModelTool'`.
- **Re-fetch `context.scene.CMT.ExporterSettings` after a reload.** A handle held across one points at a dead struct.
