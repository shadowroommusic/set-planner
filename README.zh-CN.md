# Set Planner

一个 MCP 服务器，帮你算平时要在脑子里算的那些事：**这套 set 一共多长时间**、**下一首该放什么**。

任何支持 MCP 的 agent / 客户端都可以直接使用。

[English](README.md) · 许可证：[AGPL-3.0](LICENSE)

## 功能

- **整场计时**：把每首歌的 A/B cue 换算成分段时长、衔接重叠、乐句（phrasing）提醒和总时长。
- **下一首推荐**：按 BPM（含半速/倍速）、调性兼容度、风格重合度和能量变化打分，并解释每一分。
- **不碰任何文件**：只读你给的 JSON，不打开音频文件，也不碰 Rekordbox/Serato 数据库。
- **可解释**：每条推荐都带理由、打分明细和注意事项；计时的每条警告都是明确原因，不猜。

## 环境要求

| | |
| --- | --- |
| 系统 | macOS / Linux / Windows |
| Python | 3.9 或更新 |
| 运行时依赖 | 无 |

## 安装

```sh
# 作为 Codex 插件
codex plugin marketplace add shadowroommusic/set-planner
codex plugin add set-planner@shadowroom

# 只用命令行
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/shadow-set-planner --help
```

MCP 客户端配置：

```json
{
  "mcpServers": {
    "set-planner": {
      "command": "python3",
      "args": ["mcp_server.py"],
      "cwd": "/path/to/set-planner"
    }
  }
}
```

## 输入格式

```json
{
  "tracks": [
    {
      "id": "track-1",
      "title": "Warehouse Tool",
      "bpm": 128,
      "key": "8A",
      "genres": ["techno", "melodic techno"],
      "energy": 6,
      "duration_ms": 360000,
      "cues": [
        { "name": "A", "position_ms": 15000 },
        { "name": "B", "position_ms": 210000 }
      ]
    }
  ],
  "transitions": [
    { "from": "track-1", "to": "track-2", "overlap_ms": 16000 }
  ]
}
```

`cues` 支持 `A`/`B`、`intro`/`outro`、`in`/`out`、`start`/`end` 以及带 `end_ms` 的 loop；
`key` 支持 Camelot（`8A`）或音名写法（`A minor`、`Am`、`G#m`、`Db`）；`genres` 可以是数组或逗号字符串；
`transitions` 可选。

## 工具

| 工具 | 作用 |
| --- | --- |
| `plan_set` | 给已排好序的 set 计时（`{"set": {...}, "default_overlap_ms": 16000}` 或 `{"input_path": "…"}`） |
| `suggest_next` | 推荐下一首（`{"current": {...}, "pool": [...]}` 或 `{"library_path": "…", "current_id": "…"}`） |

命令行等价：`shadow-set-planner plan`、`shadow-set-planner suggest`。

## 用法

```sh
# 给 set 计时（这里按 16 秒衔接）
.venv/bin/shadow-set-planner plan --input set.json --overlap-ms 16000 --output plan.json

# 当前这首之后放什么？
.venv/bin/shadow-set-planner suggest --library library.json --current track-1 --limit 5
```

`plan` 输出 `timeline`（分段、播放位置、cue 点、重叠）、`transitions`、`summary`（总时长、分段合计、
衔接省下的时间）与 `warnings`；`suggest` 输出带 `reasons`、`breakdown`、`cautions` 的候选列表。

## 安全说明

- 离线只读：不打开音频文件，也不碰厂商数据库。
- 只读你提供的 JSON，产物就是 JSON 文件或 stdout。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 提示缺少 A/B cue | 给曲目补 `cues`；不补也能算，会按整首长度处理。 |
| 推荐区分度不高 | 给曲目补充 `energy`/`genres`；缺失元数据按中性处理。 |
| 提示速度跳跃 | 说明这个衔接需要开启 Beat Sync 或做速度调整。 |

## 参与开发

见 [CONTRIBUTING.md](CONTRIBUTING.md)；实现细节在 [docs/internals.md](docs/internals.md)。

## 许可证

AGPL-3.0，见 [LICENSE](LICENSE)。
