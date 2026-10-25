# Data model and operators

Two settings roots, both reachable from any context with a scene:

```python
data = bpy.context.scene.CMT.ExporterSettings   # CMT_Exporter_Settings
s2b  = bpy.context.scene.CMT.S2BSettings        # CMT_S2B_Settings
```

`CMT_Exporter_Settings` lives in `cmt_exporter/properties.py`; `CMT_S2B_Settings` in `cmt_shapekey_to_bone/properties.py`. The panel is just a view of these — writing a field is equivalent to clicking it, update callbacks included.

## The four indices are derived, not settable

`CurrentGeoIndex`, `CurrentAstIndex`, `CurrentMatIndex`, `CurrentArtdefIndex` are `IntProperty(get=...)` — **read-only**. They resolve the current item from the name enum (`GeoName`, `AstName`, `MaterialName`, `ArtdefName`), which is what the UI dropdowns bind to. To select an item:

```python
data.GeoName = "MyGeo"          # not data.CurrentGeoIndex = 3
data.AstName = "MyAst"
data.MaterialName = some_material   # PointerProperty to the Material datablock
data.ArtdefName = "Units.artdef"
```

An unmatched name resolves to index 0 rather than raising — a wrong name silently selects the first item instead of failing.

Reading an enum back takes attribute access: `group.Class` gives the string, while `group["Class"]` gives the **underlying index** (and raises `KeyError` if the field was never set). Dynamic enums — `items=` is a callback — cannot be read through `bl_rna` at all: the property's `enum_items` is empty and its `default` is `''`. No enum field can be reset to empty either; assigning `""` raises `TypeError: bpy_struct: item.attr = val: enum "" not found in (...)`. To clear one, drop the item that holds it.

## GeoList — one entry per exported model file

`CMT_Exporter_PG_GeometryList`: `FileName` (str), `Class` (enum of 9 geo classes), `Geometries` (collection of `CMT_Exporter_PG_GeometryProperty`), `ActivedPropertyIndex`.

`Geometries[i].value` is a **PointerProperty to a Blender Object** (the mesh), not a name:

```python
g = data.GeoList.add()
g.FileName = "MyUnit"
g.Class = "Unit"
g.Geometries.add().value = mesh_obj      # Object, may be selected later in the UI dropdown
```

A freshly added slot has `value = None` until assigned. That is legitimate state — it is what the UI leaves when "add" runs with no mesh selected — so code walking `Geometries` must skip `None` rather than dereference it.

## AstList — the reference file

`CMT_Exporter_PG_Ast`: `FileName`, `Class` (enum from `assets/DSGs.json`'s `Classes`), `DSG`, `Geometries`, `Animations`, `Behaviors`, `ActivedPropertyIndex`.

`Ast.Geometries[i].value` is an **enum of model file names** (strings — the `FileName` of a Geo), the opposite convention from `GeoList.Geometries[i].value`. At most one geometry reference is intended per Ast.

`Ast.Animations[i]` is `CMT_Exporter_PG_AstAnimationProperty`: `AstName`, `text` (the slot name from the DSG), `value` (PointerProperty to an Action).

Three update callbacks rewrite this subtree, and they will undo hand-set state:

- Setting `Ast.Class` clears the geometry references and re-derives `DSG`.
- Setting `Ast.DSG` clears `Animations` and repopulates one slot per DSG animation slot (`item.text = <slot name>`).
- Setting `item.text` auto-fills `item.value` when an action named `<astname.lower()>_...` matches the slot text.

So fill in this order: `Class` → `DSG` → geometry reference → let `text` drive `value`.

## The other list types

- `AnimationList[i]` (`CMT_Exporter_PG_Animationlist`): `value` (Action), `Class` (enum of 6 animation classes). A slot with `value = None` aborts the animation step. To test whether an Action actually carries data use `len(action.fcurves)` plus the layered channelbags — **not** `action.is_action_layered`, which is `True` even for a freshly created empty Action.

### Which skeleton an animation binds to

The action is named after the file; the **skeleton** it binds to is decided per action *slot* in `cmt_exporter/action_data.py` `read_action_data`, which reads `bag.slot.name_display` and looks up an object of that name.

Two names therefore have to agree: the slot name and the armature object's name — because the model export writes its world bone as the armature object's name (`io_export_cn6.py`), so a mismatch means the animation never binds.

- Normally this is automatic: once a slot is bound to the armature object, `name_display` *becomes* that object's name, whatever the slot was called.
- An **unbound** slot keeps its custom name, and those are commonly `Slot_…`. Rule: a name starting with `Slot_` with characters after it is stripped to the remainder, and that remainder is used as the skeleton name. `Slot_Daniya` → `Daniya`. A name that is exactly `Slot_` is left alone. If the stripped name finds no armature, the code falls back to the raw slot name, so an armature genuinely called `Slot_Daniya` still works.
- If the name resolves to nothing, that slot is skipped silently — the animation exports with no bone data rather than failing.

- `MaterialList[i]` (`CMT_Exporter_PG_Material`): `FileName` (material name), `Class`, `Textures[i]` (`CMT_Exporter_PG_Texture`: `matName`, `Class`, `text` (the PBR slot), `value` (image name enum), `Channel`).
- `ArtdefList[i]` (`CMT_Exporter_PG_Artdef`): `Instances[i]` (`CMT_Exporter_PG_ArtdefInstance`: `Type`, `value`). The list is built from the two templates in `cmt_exporter/templates/` — `Units.artdef`, `Leaders.artdef`.

## `CMT_Exporter_PG_Texture.Channel`

Enum `("BaseColor", "Alpha")`, default `"BaseColor"`. Available on **any** texture row, not just `Opacity` — 22 of the 27 material classes in `MaterialInfo.json` have no `Opacity` slot at all.

- `BaseColor` — export the image as-is, plus the existing resolution / `WuwaNormal` handling.
- `Alpha` — at export time `extract_alpha_to_file` writes `<stem>_Alpha.png` (R=G=B=alpha, A=1, colorspace `Non-Color`) and the `.mtl` references it as a separate texture. **No inversion** — the `1-alpha` in `textures.py:127` translates Wuwa's "roughness stored in alpha" into Civ6's gloss; that is a Wuwa convention, not a general rule about alpha.
- Channel follows the **source socket** of the node link, not the filename: `Color → Base Color` is `BaseColor`, `Alpha → Alpha` is `Alpha`, and `Color → Alpha` is also `BaseColor` (that image already *is* the grayscale opacity map). `cmt.exporter_ot_automatchtextures` applies this to every still-empty row; set `data.OverwriteTextures = True` first to recompute rows that already have a value.
- A slot name is first translated through `SLOT_INPUT_ALIASES`: `Opacity`/`Alpha`/`Cutout`/`Mask` look for the BSDF **`Alpha`** input, because the Principled BSDF has no input by those names.
- One image's `Color` output can feed both `Base Color` and `Alpha` (single RGBA map). `_bsdf_inputs_reached` enumerates *all* reachable inputs rather than the first link, and for an alpha-named slot the `Alpha`-socket match wins — otherwise the `Opacity` row would get pointed at the whole colour map.
- Auto-fill at **slot-generation** time is separate and narrower: it runs once for slots named `Opacity`/`Alpha`/`Cutout`/`Mask`, and only when the BSDF `Alpha` input is fed by a TEX_IMAGE's **Alpha output socket**. It is deliberately not hooked to `value`, because a BaseColor row and an Opacity row can point at the same image. A grayscale image wired `Color → Alpha` is left for the button. Manual edits win afterwards.
- `items=` is a static tuple on purpose: a callback `items=` forces `default` to be an integer index (`TypeError: 'default' can only be an integer when 'items' is a function`).

## Operators (30, all under `cmt.*`)

Action operators — safe to call directly, no dialog:

| Purpose | Operator |
|---|---|
| **Export everything** | `cmt.exporter_ot_export` |
| Add / remove one animation | `..._addanimation` / `..._removeanimation` |
| Add all actions whose name contains `data.ActionNameToAdd` | `..._addactionsbykeyword` |
| Remove current mesh slot / reference slot | `..._removemesh` / `..._removeref` |
| Add / remove artdef instance | `..._addartdefref` / `..._removeartdefref` |
| Re-class materials by keyword | `..._modifymattypebykeywords` |
| Fill every empty texture row from the node graph | `..._automatchtextures` |
| Auto-match animation actions to Ast slots | `..._matchanimations` |

Dialog operators — they open a name prompt on `invoke`. From a script they still work, because `execute` reads a plain property; pass it, don't invoke:

```python
bpy.ops.cmt.exporter_ot_addgeometry(Name="MyUnit")   # not .invoke()
bpy.ops.cmt.exporter_ot_addast(AstName="MyUnit_Ast")
```

`cmt.exporter_ot_addmesh` acts on the current **selection** — every selected mesh is appended in one call, and a selection with no mesh adds a single empty slot.

Shape-key-to-bone (`cmt_shapekey_to_bone/`): `cmt.s2b_ot_convert`, `..._clearshapekey`, `..._editseparatemesh`, `..._autoseparatemesh`, and `..._addshapekeyanim` / `..._removeshapekeyanim`. The last two are defined in `cmt_shapekey_to_bone/panels.py`, not `operations.py`. They read `s2b`, not `data`.

Maintenance (`cmt_ordinary_tool/`): `cmt.ot_ot_removeemptyvertexgroups`, `..._removenotbindinggroups`, `..._removegroupfromvertexs`, `..._removeemptymaterialslots`, `..._removeemptyshapekeys` — all act on the selection and no-op with a warning when nothing is selected.

Updater (`cmt_updater/`): `cmt.updater_check` (read-only), `cmt.updater_run` (**destructive — see SKILL.md**).

## What `cmt.exporter_ot_export` does, in order

1. If `IsGenerateRef and IsExportAst`, validate Ast references; on error, pop up and return `{'CANCELLED'}`.
2. `IsExportModel` → for each Geo, write `<ProjectPath>/Geometries/<FileName>.fgx` (+ `.geo`). Returns `{'CANCELLED'}` if a mesh has no material.
3. `IsExportAnimation` → `<ProjectPath>/Animations/<action name>.fgx`.
4. `IsGenerateRef` → `<ProjectPath>/Assets/<FileName>.ast`.
5. `IsExportMaterial` → `<ProjectPath>/Materials/` and `/Textures/`.
6. `IsExportArtdef` → `<ProjectPath>/ArtDefs/<template name>`.

Only steps whose flag is on run. **No output directory is created** — a missing `Geometries/`, `Animations/`, `Assets/`, `Materials/`, `Textures/` or `ArtDefs/` folder makes the .NET side raise a file-not-found.
