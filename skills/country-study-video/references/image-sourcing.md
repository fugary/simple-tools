# 国家介绍配图与零版权选图规范

## 一、默认零版权风险口径

除非用户在当前对话明确放宽授权条件，否则国家介绍视频的所有配图默认严格限定在以下三类来源内：

1. **AI 原创生成**（`AI 原创生成（零第三方版权风险）`）：由当前环境可用的图像生成工具创作的无字 16:9 横图。
2. **原生公共领域 / `CC0 1.0` 摄影实景**：
   - `Wikimedia Commons`（逐条核实明确标记为 `CC0 1.0`、`Public Domain` / `PD-*` 的文件，排除 `CC BY`、`CC BY-SA`、`FAL`、`NC`、`ND`）
   - `WordPress Photo Directory`（全库原生 `CC0 1.0`）
   - `NASA Image Library`（`Public Domain (NASA)` 航天/地球/天文公有领域图库）
3. **自制矢量栅格徽章**：依据法定比例与色彩源码矢量栅格化生成的 `flag_badge.png`。

**默认禁用项**：不得混入 `Unsplash`、`Pixabay`、`Pexels` 导入图（包含早期 CC0 迁移历史条目）以及任何需要署名或相同方式共享（`CC BY`、`CC BY-SA`、`FAL`）的第三方照片。

---

## 二、史实准确性与分镜选图铁律

1. **地理分镜去手绘地图化**
   - 地理方位、岛屿、山脉与海域描述统一使用该国**可考证的真实自然景观实景摄影**，不使用 AI 手绘地图或来源不明的卡通版图，避免出现国界线或地理位置错画。
   - 审计脚本默认拦截包含 `地图` / `map` / `locator` 等可疑地图图的分镜路径。
2. **官方矢量国旗独立层展示**
   - 国旗不让 AI 重绘进全屏背景图，也不整张铺满屏幕。
   - 使用 `scripts/make_flag_badge.py` 基于官方矢量 SVG 源码（传本地 `--input` 或 `--download-flag Flag_of_<Country>.svg --save-svg ...`）按法定比例配色高精度栅格化为圆角深色描边透明 PNG（`配图/flag_badge.png`，默认宽度 `296px`，建议 `<= 307 px`，即 `1920px` 的 `16%`）。
   - 在 `lesson.json` 的 `overlays` 中声明 `cue_start..cue_end` 对应讲解区间，由 `lesson_media.py render` 自动解析 `styled.ass` 的 `StudyHintPlate` 真实底端坐标动态避让，叠加在右上安全区且不触及底部双语字幕带。
3. **互动问答“一题一图”与轻量化防剧透**
   - **默认全程一题一图**：每道互动题按题干核心对象单独选图，从提问、3.5 秒作答停顿到答句结束全程共用同一张**无字横图**，仅在答句出现文字答案（既保持视觉连贯与画面记忆锚点，又避免思考期在无关风景图之间频繁跳切）。
   - **按题型留轻量化防剧透保护**：
     - **国旗配色回忆题**：全程用该国代表性风景做底图，**提问与 3.5 秒停顿期不叠 `flag_badge.png`**，到答句开始再叠加国旗角标；
     - **单一实物近景猜名题**：若图片仅突出单一实物特写、看一眼即直接说出答案单词，改用不暴露唯一答案的同主题安静环境/远景图（可用 1 张干净通用景图或环境照承接提问与停顿，答句再切实物图），或调整提问方式为考原因/特征/用途；
     - **辨色、计数或特征观察题**：从提问起直接展示被观察对象，勿提前显示文字答案。

---

## 三、AI 配额调度与 Contact Sheet 审片流程

1. **AI 配额分级调度**
   - 部分免费/内置生图通道存在短周期限额（例如约 5 小时 2–3 张）。多集或单集缺图时先做小试确认当轮可用额度：将宝贵的 AI 原创额度优先用于极难找到精确构图实景的复合画面（如本地书桌+特色餐食、服饰纹样细节）；标志性建筑、地标、自然奇观与野生动物优先采用原生 `CC0 / Public Domain` 实景，避免在 429 限流上无效等待。
2. **候选过滤词表**
   - 检索公有领域图库时自动剔除：
     `map`, `locator`, `flag_of`, `coat_of_arms`, `emblem`, `stamp`, `postcard`, `coin`, `banknote`, `chart`, `diagram`, `signature`, `logo`, `.pdf`, `.svg`, `.tif`, `.djvu`, `passport`, `newspaper`, `stereoscop`, `glass_negative`, `lantern_slide`。
   - 优先选择现代横屏高清大图（宽高比 `>= 1.3`，宽 `>= 1200 px`），检查无水印、无边框、无内嵌文字。
3. **先网格看图，后精裁归一化**
   - 运行 `scripts/search_cc0_images.py search`（支持单条 `-q / -w / --nasa` 或批量 `--slots-json`）生成带编号、标题与授权标签的 Contact Sheet 网格图 `candidates_sheet.jpg` 及 `candidates_manifest.json`。**必须经视觉核查**确认构图主体未被切掉（尤其是高塔尖、山峰顶、人脸/动物头部），再运行 `scripts/search_cc0_images.py fetch --manifest ... --slot ... --choice ... --crop-y ...` 按需微调垂直锚点统一裁切为 `1920×1080` RGB JPEG 并自动登记 `sources.json`。

---

## 四、溯源台账与自动化核验闭环

每完成一集或更新任意配图后：
1. 在 `配图/sources.json` 中记录每张成片配图文件名对应的：`source_type`、`source_name`、`page_url`、`artist`、`license_short`、`license_url`（或 AI 模型来源说明）。
2. 运行：
   ```sh
   python scripts/write_country_sources.py --unit-dir 国家介绍视频制作/<两位编号> <中文国名>（<英文国名>） --country 国家名 --en-name CountryName
   python scripts/audit_country_assets.py --unit-dir 国家介绍视频制作/<两位编号> <中文国名>（<英文国名>）
   ```
3. 核验通过标准：全部使用图片存在且为 `1920×1080`；`sources.json` 与 `配图来源.md` 均包含最新文件 `sha256[:16]` 校验码；禁用域名与禁用授权计数均为 `0`；国旗 SVG/PNG 与 `overlays` 配置无缺漏。
