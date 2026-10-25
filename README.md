# civ6-modeltool

一份 [Agent Skill](https://docs.claude.com/en/docs/claude-code/skills)：驱动 **Civ6ModelTool** Blender 插件导出《文明6》3D 资产（`.fgx` 模型与动画、`.ast` 参考文件、贴图/材质、ArtDef XML）。

Civ6ModelTool 插件本体：[Sumcam-L/CivModelTool](https://github.com/Sumcam-L/CivModelTool)

## 装什么

skill 会读插件的设置结构（`bpy.context.scene.CMT.ExporterSettings` / `S2BSettings`）、跑导出、跑型态键转骨、清理网格，以及按错误字符串定位导出失败原因。它**不含**插件代码——插件需另行安装。

## 安装

```bash
npx skills add Sumcam-L/civ6-modeltool-skill
```

或手动放进任一被扫描的 skill 根目录（只认一层，不递归）：

| 作用域 | 路径 |
| --- | --- |
| 用户 | `~/.agents/skills/civ6-modeltool/` |
| 用户 | `~/.dsh/skills/civ6-modeltool/` |
| 项目 | `<project>/.agents/skills/civ6-modeltool/` |
| 项目 | `<project>/.dsh/skills/civ6-modeltool/` |

装好后目录里出现 `civ6-modeltool` 即生效，无需重启。

## 怎么用

```
/civ6-modeltool
```

该 skill 带 `disable-model-invocation: true`，只接受用户显式调用，模型不会自己挑它。这是刻意的：触发它意味着要动真实工程和 Blender 场景。

## 内容

| 文件 | 用途 |
| --- | --- |
| `SKILL.md` | 入口：分支决策（导出 / 型态键转骨 / 清网格 / 排错）、前置约束、热重载流程 |
| `reference/api.md` | 两个设置根的全部字段、30 个 `cmt.*` 算子、派生索引的只读语义 |
| `reference/model-requirements.md` | 网格硬性要求、报错原文、插件不校验的项（骨骼数上限、类兼容性） |
| `reference/troubleshooting.md` | 按报错字符串排序的故障排查 |
| `scripts/preflight.py` | 只读体检脚本，导出前跑，输出 `PREFLIGHT {json}` |

## 前置条件

- **仅 Windows + Blender。** 导出器在导入期加载四个 .NET 程序集（`Firaxis.Utility`、`Firaxis.Granny`、`Firaxis.Granny.Impl`、`CivNexus6`），在 Blender 外导入必然报错，别用 `pip install` 去"修"。
- **Civ6 工程目录存在。** `ProjectPath` 必须指向含 `Assets/` 的目录，且该目录树由 Civ6 AssetEditor 创建——插件不建目录。

## 注意

`cmt.updater_run` 会用 GitHub `main` 覆盖整个插件目录，本地改动会丢。对工作副本永远别调它；`cmt.updater_check` 只读，安全。
