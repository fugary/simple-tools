# `project.json` 数据结构规范

`init_remotion_project.py` 会将上游产出的 `timeline.json`、`scenes.json`、`复习主题.json` 和音频时长自动整理为 `src/data/project.json`。你也可以直接编辑该文件，按教学意图增删 HUD、Spotlight 与转场特效。

```json
{
  "meta": {
    "title": "China — A Great Country with a Long History",
    "subtitle": "Bilingual Study Video",
    "fps": 30,
    "width": 1920,
    "height": 1080,
    "durationInSeconds": 417.0,
    "durationInFrames": 12510,
    "audioFile": "audio/narration.wav"
  },
  "scenes": [
    {
      "id": "scene-0",
      "title": "长城",
      "imageFile": "images/长城.jpg",
      "start": 0.0,
      "end": 23.86,
      "transition": "fade",
      "transitionDurationFrames": 18,
      "backdropDim": 0.48,
      "vfx": {
        "kind": "none"
      }
    }
  ],
  "cues": [
    {
      "index": 0,
      "en": "It is one of the largest countries in the world.",
      "zh": "它是世界上领土面积最大的国家之一。",
      "start": 19.38,
      "speechEnd": 21.86,
      "end": 23.86,
      "notes": [
        "one of the + 最高级 + 复数名词，表示“最……的……之一”。"
      ],
      "highlightEn": ["one of the largest countries"],
      "highlightZh": ["最大的国家之一"],
      "reviewTopic": null,
      "chapter": "Geography & Scale"
    }
  ],
  "spotlights": [
    {
      "id": "dumplings-focus",
      "start": 250.0,
      "end": 258.0,
      "x": 0.5,
      "y": 0.68,
      "radiusX": 0.22,
      "radiusY": 0.14,
      "dimOpacity": 0.38,
      "label": "Dumplings"
    }
  ],
  "hud": [
    {
      "id": "everest-hud",
      "kind": "metric_climb",
      "start": 46.58,
      "end": 59.46,
      "position": "top-right",
      "eyebrow": "WORLD'S HIGHEST PEAK",
      "title": "Mount Qomolangma",
      "fromValue": 0,
      "toValue": 8849,
      "unit": "m",
      "badge": "#1 Highest Peak"
    },
    {
      "id": "area-hud",
      "kind": "comparison_bars",
      "start": 19.38,
      "end": 23.86,
      "position": "top-right",
      "title": "Land Area (Million km²)",
      "items": [
        { "label": "Russia", "value": 17.1 },
        { "label": "Canada", "value": 9.98 },
        { "label": "China", "value": 9.6, "accent": true },
        { "label": "USA", "value": 9.37 }
      ]
    },
    {
      "id": "yangtze-hud",
      "kind": "route_flow",
      "start": 59.46,
      "end": 64.26,
      "position": "top-right",
      "title": "Yangtze River · 6,300 km",
      "steps": ["Qinghai-Tibet Plateau", "Three Gorges", "East China Sea"]
    },
    {
      "id": "flag-overlay",
      "kind": "flag_badge",
      "start": 32.34,
      "end": 37.14,
      "imageFile": "images/flag_badge.png"
    }
  ],
  "overlays": [
    {
      "id": "cover-hero",
      "kind": "cover_hero",
      "start": 0.0,
      "end": 5.3,
      "eyebrow": "COUNTRY STUDY · CHINA",
      "title": "CHINA",
      "subtitleEn": "A Great Country with a Long History",
      "subtitleZh": "历史悠久的伟大国度",
      "sealText": "中国",
      "svgPreset": "great_wall"
    }
  ]
}
```

## 字段说明

* **`scenes[].backdropDim`**：可选 `0.0 ~ 0.9` 的深色渐变蒙版不透明度。当该场景上方叠加了构图级图形卡片（如地球仪、面积对比、书法气泡、三级阶梯）时建议设 `0.45~0.68` 提升可读性；直出风景主角图（如珠峰、长江航拍）可设 `0.0~0.20`。
* **`scenes[].vfx`**：
  * `{"kind": "none"}`：纯静态高清实景（默认推荐）。
  * `{"kind": "motes", "count": 18, "opacity": 0.32}`：轻量 SVG 漂浮微光粒子（无像素扭曲）。
  * `{"kind": "screen_video", "videoFile": "vfx/steam_loop.mp4", "opacity": 0.55, "region": {"x": 0.5, "y": 0.52, "w": 0.36, "h": 0.42}}`：使用真实黑底透明混合视频素材，通过 `<OffthreadVideo>` + `mixBlendMode: "screen"` + 径向柔边遮罩局部叠加（彻底替代格子烟雾）。
* **`cues[].end`**：由 `init_remotion_project.py` 自动按下一句 `start` 计算填充（最后一句延伸至音频末尾），确保停顿期间字幕保持显示。
* **`cues[].chapter`**：可选章节标签（如 `"Introduction"` / `"Capital City"`）；无 `reviewTopic` 时，左上角面包屑胶囊会显示当前 `chapter`。
* **`cues[].richEn` / `richZh` / `richNotes`**：由 `init_remotion_project.py --ass` 从 `styled.ass` 解析生成的精确分段数组（`{ text, highlight }[]`），用于 1:1 还原重点词高亮与 `StudyHintLabel` 音标局部变色；未提供 `.ass` 时自动回退到 `highlightEn` / `highlightZh` 与 `notes`。
* **`spotlights`**：坐标与半径均为 `0.0 ~ 1.0` 归一化比例，用于在讲解关键物品时柔和羽化聚焦画面局部。
* **`overlays`（10 种构图级动态图形预设）**：完整联合类型定义见 `templates/src/types.ts` 中的 `GraphicOverlayItem`：
  1. `cover_hero`：封面大标题 + 可选描边长城 SVG（`svgPreset: "none"` 可关闭）+ 正向 `0°` 印章。
  2. `globe_fact_card`：可选旋转 3D 经纬线地球仪（`showGlobe: false` 可关闭）+ 交错进入的国家档案卡片。
  3. `area_infographic`：双栏 `9.6M km²` 跃升统计卡 + 四国面积横向对比柱状图。
  4. `blueprint_callout`：地标名片 + 可选建筑蓝图线条渐绘动画（`svgPreset: "none"` 可关闭）。
  5. `calligraphy_bubbles`：书法印章圆盘（`centerText`）+ 周边漂浮语汇气泡。
  6. `waving_flag_showcase`：可选正弦逐条动态飘扬五星红旗（`showFlagGraphic: false` 可关闭）+ 国家象征解说卡。
  7. `terrain_profile`：无外框开放画布自西向东“第一/二/三级阶梯”SVG 剖面与节点卡片。
  8. `elevation_ruler`：右侧垂直 `0 → 8,849m` 海拔标尺 + 山顶信标脉冲圈。
  9. `river_course_hud`：左侧 `6,300+ km` 跃升数字卡 + 流域里程停靠点轨道。
  10. `qa_quiz`：互动问答卡，`qStart` 显示问题与思考提示，`aStart` 弹出双行绿色答案卡（`✓ aEn` 第一行，`aZh` 第二行）。
