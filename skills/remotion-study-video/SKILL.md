---
name: remotion-study-video
description: 基于 Remotion (React + TypeScript) 制作双语教学动效视频。自动接入上游产出的 timeline.json、scenes.json、narration.wav、复习主题.json 与高清配图，以“高清稳定实景底图 + React 磨砂玻璃 HUD 数据卡 + 局部聚光聚焦 + @remotion/transitions 转场 + 双语高亮字幕 + 可选实拍透明/Screen 叠化素材”替代 image-motion 与手写 CDP 截图脚本。
---

# 双语教学 Remotion 动效视频（Remotion Study Video）

将已定稿、已完成配音与时间轴对齐的双语教学工程，一键脚手架化为标准 **Remotion (React + TypeScript)** 视频工程，支持 **Remotion Studio 实时拖拽/逐帧预览**、**15 秒样片快速验证** 与 **1080p/30fps MP4 确定性渲染**。

## 与现有技能的分工边界

| 阶段 | 负责技能 | 是否保留 |
| :--- | :--- | :--- |
| 教研文本、事实核查、Word/PDF 讲义、镜像目录约定 | `bilingual-article-teaching`、`country-study-video` / `textbook-unit-video` | ✅ **完全保留** |
| 无版权高清找图 / 生图、Lily 配音与 ASR 体检 | `country-study-video`、`teaching-slideshow-video` (`narrate` / `audit_narration.py`) | ✅ **完全保留** |
| 语义断行、词汇高亮与顶部语法提示规则 | `bilingual-study-subtitles`（产出 `styled.ass` / `<编号> ... .ass` 与 `timeline.json`） | ✅ **保留规则与数据** |
| 单图 2D 像素位移、正弦波烟雾/水波 | `image-motion` | ❌ **本流程不用** |
| 视频动效编排、HUD、转场与成片输出 | **`remotion-study-video`（本技能）** | ✅ **唯一动效渲染出口** |

---

## 核心设计铁律（延续并升级视觉规范）

1. **禁止假动效与物理扭曲**：
   - 严禁对风景、建筑、餐桌、人物照片施加 2D 正弦波扭曲（水波、格子热气、树叶乱颤）；
   - 实景摄影底图默认 **100% 稳定锁定（`scale: 1.0`）**，不盲目对大山大城做机械推拉导致眩晕。
2. **用“教学视觉引导”代替“底图乱动”**：
   - **局部聚光聚焦（Spotlight Callout）**：讲到具体事物（如饺子、长城烽火台）时，柔和压暗周边并聚焦框选主体区域；
   - **真实黑底材质叠化**：若确需热气/飘雪/光斑氛围，使用实拍黑底循环短片配合 `<OffthreadVideo>` + `mixBlendMode: "screen"` + 径向柔边遮罩，或使用轻柔的 SVG/Lottie 矢量微粒；
   - **现代通透 HUD 叠加层**：通透半透明深色玻璃（`rgba(15, 23, 42, 0.44)` + `1.5px solid rgba(255,255,255,0.24)`，不施加全卡背景毛玻璃以免糊灰风景），用 `spring()` 与连续缓动曲线呈现海拔攀升、面积对比柱状图、路线节点轴、双行互动问答 `qa_quiz` 等。
3. **无白框电影级双语字幕与音标解析条**：
   - 支持通过 `--ass` 直接读取 `bilingual-study-subtitles` 的 `styled.ass`（保留精确逐词 `#FF7B25` 高亮与 `StudyHintLabel` 局部变色音标解析，存储于 `richEn` / `richZh` / `richNotes`）；回退模式使用 `highlightEn` / `highlightZh`；
   - `notes` 顶部语法提示与左上角 `Review | <Topic>` 胶囊避让安全区，长句自动安全限宽与响应式字号收束，杜绝溢出裁切。
4. **渲染前全片审计 + 先样片后全片**：
   - 修改 `project.json` 后**必须先运行 `audit_layout.py`** 按 `0.25s` 步长扫描全片碰撞（`StudyHint`、HUD/Overlay 卡片、字幕区 `y>=825`、`qa_quiz` 绿框双行宽度与画幅越界），全部通过后再运行 `npx remotion studio` 预览或 `--frames=0-450` 样片导出。

---

## 标准执行流程

### 步骤 1：环境检查
确认本机已安装 Node.js (>= 18)、npm/npx 与 FFmpeg：
```bash
python3 /Users/gary/Documents/simple-tools/skills/remotion-study-video/scripts/check_environment.py
```

### 步骤 2：一键初始化 Remotion 工程（兼容最新 `country-study-video` 目录规范）
直接传入最新 `country-study-video` 单集根目录 `--episode-dir`（如 `国家介绍视频制作/<两位编号> <中文国名>（<英文国名>）/`），或传统 `成片工程/` 目录 `--build-dir`：
```bash
python3 /Users/gary/Documents/simple-tools/skills/remotion-study-video/scripts/init_remotion_project.py \
  --episode-dir "/path/to/国家介绍视频制作/01 中国（China）" \
  --dest "/path/to/项目/remotion_studio" \
  --title "China — A Great Country with a Long History"
```
- 脚本会自动发现 `成片工程/timeline.json`、`复习主题.json`、`配图/` 与重命名后的最终字幕 `.ass`（`<编号> ... .ass` 或 `styled.ass`）；
- 若上游已按最新版 `country-study-video` 精简了 `成片工程/`（删掉了 `scenes.json` 与 `narration.wav` 缓存），会自动根据 `lesson.json` / `分镜.json` + `timeline.json` + `配音/*.wav` 原生重建分镜时间与合成音轨；
- 如需手动指定，也可单传 `--build-dir`、`--timeline`、`--ass`、`--scenes`、`--audio`、`--images-dir`、`--review-topics`。
- 配合新版 `country-study-video` 复习卡规范：若配置 `reviewTopic` 切换复习卡，首句台词应明确读出卡片主题/对象名称。
初始化后安装依赖（仅首次需要）：
```bash
cd "/path/to/项目/remotion_studio" && npm install
```

### 步骤 3：配置动效脚本（构图级图形叠加层、HUD、聚光聚焦与转场）
编辑 `src/data/project.json`（完整结构见 [data-schema.md](references/data-schema.md)，视觉原语见 [design-and-effects.md](references/design-and-effects.md)）：
- **`overlays`（重点推荐，避免“纯文字堆砌”）**：按教学段落配置构图级动态矢量/数据图形叠加层，共 10 种预设：
  - `cover_hero`：封面大标题 + 描边动画长城 SVG（实景已含地标时可设 `svgPreset: "none"`）+ 正向 `0°` 印章；
  - `globe_fact_card`：旋转 3D 经纬地球仪（可选 `showGlobe: false`）+ 交错渐入的国家信息档案卡；
  - `area_infographic`：双栏领土面积跃升卡 + 横向对比柱状图；
  - `blueprint_callout`：地标卡片 + 天坛等建筑蓝图渐绘动画（可选 `svgPreset: "none"`）；
  - `calligraphy_bubbles`：书法圆印（如“中文”）+ 多语言浮动气泡；
  - `waving_flag_showcase`：物理波浪飘扬五星红旗（可选 `showFlagGraphic: false`）+ 国家象征双语卡片；
  - `terrain_profile`：无外框开放画布中国西高东低三级阶梯地理剖面动画；
  - `elevation_ruler`：垂直 `0 → 8,849m` 海拔标尺 + 山顶信标脉冲；
  - `river_course_hud`：`6,300+ km` 长江跃升卡 + 流向里程轨道；
  - `qa_quiz`：互动问答卡（先显示 `🤔 Think about it... 想一想`，到 `aStart` 弹性展开严控双行的绿色答案框：`✓ aEn` 与 `aZh` 分行独立不溢出）。
- **`scenes[].backdropDim`**：当该场景承载矢量图形叠加层时，设置 `0.45~0.68` 柔和压暗实景底图（如长城/珠峰等直出高清场景可保留 `0.0~0.18`）。
- **`cues[].chapter`**：为每句字幕标记所属章节名称，左上角胶囊优先显示 `Review | <reviewTopic>`，其次显示 `chapter`；顶部自动附带全片渐变进度条。
- **`scenes[].transition`**：配置 `"fade"`（默认交叉溶解）、`"slide"` 或 `"wipe"`；
- **`spotlights`**：按时间段框出照片重点区域（如 `x: 0.48, y: 0.68, radiusX: 0.22, radiusY: 0.16`），讲到对应词汇时柔和羽化聚焦；
- **`hud`**：轻量化角落补充 HUD（`"metric_climb"` / `"comparison_bars"` / `"route_flow"` / `"flag_badge"`）；开场封面统一通过 `overlays` 中的 `cover_hero` 呈现（不再在正片开场额外叠加居中黑底回退封面框）；
- **`scenes[].vfx`**：可选叠加 `"motes"`（柔和矢量光斑）或指向 `public/vfx/` 下的实拍黑底 Screen 混合视频（如热气、飘雪）。

### 步骤 4：布局防撞审计、预览与渲染（先审计+样片，后全片）
1. **渲染前全片布局与溢出审计（必做，数秒内拦截遮挡与超框）**：
   ```bash
   python3 /Users/gary/Documents/simple-tools/skills/remotion-study-video/scripts/audit_layout.py \
     --project "/path/to/项目/remotion_studio/src/data/project.json"
   ```
2. **启动 Remotion Studio 实时预览（推荐先确认动画与排版）**：
   ```bash
   cd "/path/to/项目/remotion_studio" && npm run studio
   ```
3. **渲染 15 秒样片快速验收（例如 0~450 帧，或指定片段帧范围）**：
   ```bash
   npx remotion render StudyVideo out/sample.mp4 --frames=0-450
   ```
4. **渲染全片 1080p/30fps 成片**：
   ```bash
   npx remotion render StudyVideo out/final_remotion.mp4
   ```
   > 若多核机器内存充足，可通过 `--concurrency=50%` 调节并发数兼顾速度与内存占用。

### 步骤 5：成片自动化体检与抽帧目检
```bash
python3 /Users/gary/Documents/simple-tools/skills/remotion-study-video/scripts/verify_render.py \
  "/path/to/项目/remotion_studio/out/final_remotion.mp4" \
  --expected-duration <总秒数> \
  --contact-sheet "/path/to/项目/remotion_studio/out/contact_sheet.jpg"
```
查看生成的 `contact_sheet.jpg`（含封面、高光句、HUD、顶部语法提示、复习段、片尾 6 张关键帧拼图），确认无字幕溢出、无文字遮挡、音画时长一致后交付。
