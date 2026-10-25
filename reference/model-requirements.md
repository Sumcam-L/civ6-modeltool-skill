# What a Civ6 mesh must satisfy

`cmt_exporter/io_export_cn6.py` writes the intermediate `.cn6` text the .NET side consumes. Both layers enforce requirements, and the failures are loud. Check these before exporting rather than after.

## Hard requirements on each mesh

| Requirement | Where enforced | Failure if violated |
|---|---|---|
| Parented to an armature (`obj.parent.type == 'ARMATURE'`) | `cmt_exporter/operations.py` `export_models` | Mesh **skipped**, warning `模型 [X] 跳过未绑定骨架的网格: <names>`. Not fatal — other Geos still export. |
| ≥1 material slot, none with `material is None` | `export_models` pre-check + `io_export_cn6.py` `do_export` | Export returns `{'CANCELLED'}` with `网格 [X] 缺少材质: Civ6 模型要求每个网格至少有一个材质`, or raises the same text as a `ValueError`. |
| ≥1 UV layer | `io_export_cn6.py`: `mesh.calc_tangents(uvmap = mesh.uv_layers[0].name)` | `IndexError` — the call has no empty check. |

Bone weighting is self-healing: weights are renormalized to a total of 255 across the top 8 influences per vertex, extra influences dropped, missing ones zero-filled with weight 0. A vertex in no group gets `-1` ids with `0` weights — allowed, and the "unweighted vertices" error is commented out at `io_export_cn6.py:507`.

Two Blender defaults trip the table above when you build meshes from script: `bpy.data.meshes.new()` produces a mesh with **no UV layer**, and `bpy.data.armatures.new()` produces an armature with **no bones**. Add a UV layer (`mesh.uv_layers.new(name="UVMap")`) and create bones in edit mode — `bpy.ops.object.mode_set(mode="EDIT")`, `arm.data.edit_bones.new(...)`, then back to `OBJECT`. A bone-less armature makes `io_export_cn6.py:168` subscript `armature.bones[0]` and raise `IndexError`.

## Requirements the plugin does *not* enforce

- **Bone count limits: 60 for Unit, 256 for Leader.** These are game-side. The plugin's only bone-count field is `s2b.MaxBones`, which affects `cmt.s2b_ot_autoseparatemesh` and nothing in the export path. A model over the limit exports cleanly and fails in Civ6.
- **Class compatibility.** `validate_ast_references` only runs when both `IsGenerateRef` and `IsExportAst` are on; with that off, a mismatched pairing exports fine and breaks at runtime.
- **UV layer count vs. what the game wants.** `UVCount` (1–3) selects the template `cmt_exporter/templates/uv<N>.fgx`. Read the field's own description before advising: **2 layers loses bone binding**; 3 is the way to get the second-UV features (ambient occlusion, lightmaps) while keeping the rig. Extra UV layers are exported as `uv0`/`uv1`/`uv2` when present.

## Conventions applied on export

- **Scale 100×**, Z-up → Y-up. `SCALE = 100.0` in `io_export_cn6.py`; this is why a Blender unit is a Civ6 metre/centimetre boundary worth checking if a model arrives the wrong size.
- **Axis conversion** is handled by the exporter, so a model built Z-up in Blender needs no manual rotation.
- Custom split normals survive only when the mesh carries a `VERTEX_KEYS` vertex group plus the `originalTangentsBinormals` custom property — that is the round-tripped state produced by the importer. `calc_tangents` otherwise **wipes custom normals**, as its own comment says.
- Triangulation is opt-in (`IsTriangulation`); already-triangulated meshes don't need it.

## Class pairing

`cmt_exporter/assets/AllowedClasses.json` is the single source of truth for which geo/animation classes an Ast class accepts — `cmt_exporter/allowed_classes.py` loads it at import. Read that file, don't recall the table from memory; it is small and changes independently of code. Both the model panel and the export validation consult it.

The Geo class enum and the Ast class enum are *different sets* — `cmt_exporter/enum_items.py:get_geotype_items` (9 geo classes) is not `get_ast_class_items` (16 ast classes, from `assets/DSGs.json`). Comparing a value from one against the other is a common mistake.

## Animation

- The animation's `Class` must be allowed by the Ast's class, and the action's name must relate to the Ast name: the auto-matcher only considers actions containing `<astname.lower()>_`, then matches the remainder against the slot text (`cmt_exporter/properties.py` `anim_text_update`, same rule in `cmt.exporter_ot_matchanimations`).
- **The skeleton is chosen by the action slot's name, not the Ast name** — an unresolvable slot is dropped silently. See [api.md](api.md) § Which skeleton an animation binds to.
- Duration is derived from the action's frame range and the scene fps.
- `Compress` is on by default.

## Project tree

The export writes into an existing Civ6 project tree. **No directory is created** — the plugin assumes `Assets/`, `Geometries/`, `Animations/`, `Materials/`, `Textures/`, `ArtDefs/` already exist, and creating project structure is AssetEditor's job (run it once). This is deliberate; don't paper over a missing directory by creating it in a probe script and then reporting the export healthy.
