---
name: textbook-unit-video
description: 将教材双语学习文档、补充词句清单等原始素材，经合并查重、两轮教学标注与防歧义精修、文本冻结门禁、场景契合配图、Lily 逐句配音与 ASR 体检、双语字幕合成及新加坡 V2 风格 Word/PDF 打印讲义导出，端到端制作新单元英语课文教学视频。适用于小学高年级至初中英语教材单元课文视频的完整制作与返修。
---

# 英语课文单元视频端到端制作

本技能沉淀自第一至第五单元课文视频工程实战，统筹衔接 [bilingual-article-teaching](../bilingual-article-teaching/SKILL.md)、[teaching-slideshow-video](../teaching-slideshow-video/SKILL.md) 与 [bilingual-study-subtitles](../bilingual-study-subtitles/SKILL.md)，通过**“先合并查重、两轮审校冻结文本，再并行配图配音、严格抽帧验收，最后回填成片时间戳出打印讲义”**的硬门禁流水线，避免因改文或图文不符引起的返工。

## 目录与交付约定

- **制作工程目录（统一 4 文件 + 4 目录标准）**：`课文视频制作/<单元名及主题>/`
  - 单元根目录**仅放**：
    - `lesson.json`（全单元唯一核心源，含 `cues` 与 `scenes`）
    - `narrated.json`（含 `audio` 相对路径的配音清单）
    - `front_matter.json`（首页档案、速查表、音标词表与章节映射）
    - `打印同页对照.json`（关联句组同页约束）
    - `配图/`（仅留 `lesson.json["scenes"]` 实际引用的图片）
    - `配音/`（仅留 `narrated.json` 实际引用的英文 WAV）
    - `成片工程/`（仅留轻量时间轴与字幕工程：`timeline.json`、`<单元名>.ass`、`<单元名>.srt`、`顶部提示分行.json`、`章节时间.txt`；视频交付验收后清理 `视频片段/`、`字幕画面/`、`完整画面.h264`、`完整配音.wav` 及重复 `.mp4`/开篇预览）
    - `开发记录/`（统一归档原始底稿、素材查重报告、`分镜.json`、`疑难读音识别.json`、`疑难读音复核.json`、`逐句配音核查.json`、`成片验证.json`、核对单 `.md`/`.txt` 等过程留痕，**不得散落在单元根目录**）
  - 跨单元汇总排查笔记统一放入 `课文视频制作/汇总记录/`。
- **最终交付目录**：`课文视频输出/<单元名及主题>/`
  仅发布三件成品：`<单元名及主题>.mp4`、`<单元名及主题> 双语学习讲义（打印版）.docx` 及同主干 `.pdf`。制作目录**不再保留**单独的“制作版” Word。

---

## 六阶段硬门禁流程

> **铁律**：阶段 1–2 文本未通过校验并冻结前，**严禁**启动阶段 3–5 的配图生成、配音合成与视频渲染；阶段 3 配图未对照文字逐条过审前，**严禁**进入合成烧录。

### 阶段一：多源素材合并、查重与底稿清洗

1. **全量抽取并区分来源**：从用户提供的课文学习文档（TXT/MD/Word/RTF）和补充清单（词组表、句型表、练习页）中按教材顺序抽取单元目标、对话、短文/日记、练习指令、填空题与语音板块（Phonics），在工作笔记中标记“课文原句 / 补充清单 / 教学补例”。
2. **合并查重（去冗余不丢教学）**：运行 [merge_and_audit_materials.py](scripts/merge_and_audit_materials.py) 对主稿与补充清单做规范化比对（输出 `--out 开发记录/素材合并查重.json`，**不覆盖原文件**）：
   - **完全重复且无新对比目的**：确认原句已收录即可，不重复朗读；
   - **有教学对比目的的重复**：如换主语/否定对比、原句紧跟短语跟读、词形变化链（`swim → swimming → swimmer`）、易混词辨析，**保留各自独立条目**并归入同页对照候选。
3. **预处理朗读与填空标记**：由同一份 `开发记录/素材合并查重.json` 报告中的 `blank_slots_needing_spoken_or_pause` 与 `tricky_pronunciation_candidates` 字段，提前识别并准备 `spoken`：
   - **填空题**：`en`/`zh` 保留 `_____`、`（   ）`、方框；句末填空用 `pause`（如 `3.5` 秒）留作答时间，句中填空在 `spoken` 中规划为前后分段朗读 + 中间静音，绝不读出 `blank`、`underscore` 或答案。
   - **专名与缩写**：中文拼音人名（如 `Xiaoxiao`、`Lanlan`、`Wendi`、`Haotian`）、`sb./sth.`、年份、小数、英文字母/连字符缩略词提前给出展开或分音节 `spoken` 建议。

### 阶段二：两轮教学标注精修、防歧义核查与文本冻结

按 [质量门禁与核查细则](references/quality-gates.md) 完成两轮审查后再冻结文本：

1. **第 1 轮（教学准确与高亮配对）**：
   - 原句首次出现就地用通俗中文给出读懂它所需的 `notes`；
   - 补齐 `highlight_en` / `highlight_zh`（严格 1:1 数量与语义对齐，禁止截断在 `learn to`、`is located`、孤立冠词/介词上；多高亮句逐条核对；译序冲突且独立考查时拆成相邻条目）；
   - 建立 `打印同页对照.json`（每组 2–8 条紧密相关条目，严禁跨越章节边界）。
2. **第 2 轮（孩子视角防读反复查 + 首页元数据）**：
   - 遮住译文从六年级学生视角复述每条 `notes`，排查**语法条件以偏概全、时间起点方向模糊、否定范围漏标、问句预设偏差、缺反例语境、长提示缺少自然断句点**等 6 类歧义；
   - 编写 `front_matter.json`：单元小档案 `facts`、首页代表表达速查 `quick_refs`（8–9 项）、核心难词表 `vocab_table`（6–7 词，含美式音标 `/.../`、词性、句中义与首现条目号）和 `chapter_map`（时间戳先留空或暂估，待阶段六回填实测时间）。
3. **硬门禁校验与冻结**：
   - 运行 `bilingual-article-teaching/scripts/study_cues.py lesson.json --groups 打印同页对照.json --check-narration`（新制作单元默认加 `--strict`，确认 0 错误；若教材原句确需保留特定格式省略号等，在核查说明中显式登记例外）；
   - 先用 [build_unit_handout.py](scripts/build_unit_handout.py)（传 `--no-pdf` 或临时导出初版 PDF）过目首页不溢出、无错别字后，**正式冻结 `lesson.json` 的 `en`、`zh`、`highlight_*` 与 `notes`**。

### 阶段三：场景契合的分镜规划与配图验收

遵循“一景一图、随文切景、先审后合”，详见 [质量门禁与核查细则](references/quality-gates.md) 第三节：

1. **按场景与知识进展规划 `开发记录/分镜.json` 并同步到 `lesson.json`**：
   - 严禁按固定秒数机械切图；只在**地点切换、角色/动作变更、实验阶段推进、日记日期转换**时换图（`cue` 为 0 起始下标且严格递增），最终同步写入 `lesson.json` 的 `scenes` 字段；
   - 观察日记、科学实验或流程步骤类课文（如植物发芽日记、操作步骤），**每个关键日期/阶段各配独立场景图**，保证画面随文字进度推进。
2. **生图与逐条图文一致性审查**：
   - 图片采用 16:9 横构图、自然场景铺满画面，**不把文字、编号或空白字幕框画进图片**；
   - 所有新图与复用图生成后，**逐条对照 `开发记录/分镜.json` 与对应 `cues` 目视检查**：核对物体数量、颜色、动作方向、科学原理及安全规则正反示范是否与文字完全相符；**不符文字场景的图当场重绘或替换，绝不带病进入渲染**。

### 阶段四：Lily 逐句配音、填空静音拼接与 Whisper ASR 体检

1. **合成英文配音**：`lesson.json` 中 `voice` 设为 `"Lily"`、`rate` 设为 `"native"`（**不可填数字 `1.0`**，否则 `lesson_media.py` 会拒跑），普通句 `pause: 2.0`，作答留白句 `pause: 3.5`；调用 `teaching-slideshow-video/scripts/lesson_media.py narrate --manifest lesson.json --out narrated.json --cache 配音`（若修改 `spoken` 后重跑，先删旧 `narrated.json`，`配音/` 缓存会自动复用）。
2. **句中填空与专名精细处理**：
   - 句中留白题分段合成前后音频并在空位插入静音，写入该条 `audio`；
   - 运行 `teaching-slideshow-video/scripts/audit_narration.py --manifest narrated.json --report 开发记录/逐句配音核查.json` 完成电平/时长检查与本地 `mlx-whisper` ASR 相似度核验，疑难读音复听结果记入 `开发记录/疑难读音复核.json`。
3. **微调边界**：对低相似度、句首短词或中文拼音人名切片复听；**只允许调整 `spoken` 重录，不得改动已冻结的 `en`/`zh` 显示稿**。

### 阶段五：时间轴拼接、字幕精排、烧录与实帧抽检

1. **拼接音频与生成时间轴**：运行 `teaching-slideshow-video/scripts/lesson_media.py prepare --manifest narrated.json --out-dir 成片工程`（要求 `成片工程` 尚不存在；如只需微调字幕/换行，勿重跑 `prepare`，直接改 `顶部提示分行.json` 后重跑 `format_subtitles.py` 与 `render --overwrite`）生成 `narration.wav`、`layout-reference.mp4`、`mobile-style.json`、`成片工程/timeline.json`、`scenes.json` 与 `timing.json`。
2. **双语字幕与顶部提示底板排版**：
   - 运行 `teaching-slideshow-video/scripts/build_subtitles.py --build 成片工程 --font-zh "Heiti SC" --font-en "Arial"` 生成基础 `study.ass` / `study.srt`；
   - 长提示按语义断行写入 `成片工程/顶部提示分行.json`（保证固定词组和引号释义完整），运行 `teaching-slideshow-video/scripts/format_subtitles.py --build 成片工程` 生成带顶部 10% 磨砂学习底板与底部 66%–90% 渐变浅底的 `成片工程/styled.ass`。
3. **烧录、章节封装与关键帧实查**：
   - 执行 `teaching-slideshow-video/scripts/lesson_media.py render --build 成片工程 --ass 成片工程/styled.ass --output "课文视频输出/<单元名及主题>/<单元名及主题>.mp4"` 完成烧录与整片解码校验（注意脚本会在输出目录旁生成 `.verification.json`，需在步骤六移入 `开发记录/`）；如需为 MP4 写入章节书签，按 `章节时间.txt` 用 `ffmpeg -map_metadata` 无损封装章节；
   - 执行 `teaching-slideshow-video/scripts/verify_video.py --mp4 "课文视频输出/<单元名及主题>/<单元名及主题>.mp4" --build 成片工程 --out-dir 成片工程/抽帧核验` 导出关键帧拼图及 `854×480` 手机横屏图，**抽帧实看**：多高亮句、修订过歧义的提示句、日记/实验图文切换点及填空题作答画面，确认无遮挡、无换行断裂、图文同步。

### 阶段六：回填成片时间戳、生成 V2 打印讲义与终审交付

1. **生成 V2 打印讲义 Word 与原生 PDF**：
   - 确认 `成片工程/timeline.json`（或外层 `实测时间轴.json`）与 `front_matter.json` 就绪后，运行 [build_unit_handout.py](scripts/build_unit_handout.py)：
     ```sh
     python3 .agents/skills/textbook-unit-video/scripts/build_unit_handout.py --unit "<单元名及主题>"
     ```
   - 脚本按 `国家介绍` 新加坡 V2 样式（品牌蓝 `#1D4ED8` 高亮、暖砖红 `#9A3412` 要点与美式音标、0.95 cm 悬挂缩进、首页三张表、章节右对齐成片时间、同页编排）生成 `课文视频输出/<单元名及主题>/<单元名及主题> 双语学习讲义（打印版）.docx`，并调用本机 Microsoft Word 导出同名 `.pdf`。
2. **PDF 自动化验收与目视抽检**：
   - 脚本自动调用 `bilingual-article-teaching/scripts/verify_pdf_handout.py` 校验汉字完整、无康熙部首乱码、首页不溢出第 2 页、末页无孤立单条尾巴、全集条目与 `打印同页对照.json` 全部同页；
   - 渲染 PDF 首页、第 2 页与末页图片目视抽查确认美观无错位。
3. **归档验证记录与瘦身清理**：将 `lesson_media.py render` 产生的 `.verification.json` 合并或移入 `开发记录/成片验证.json`（记录条目数、总时长、分镜/配图数、ASR 复核、高亮核对、打印页数、抽帧数）；确认成片和讲义验收无误后，整理 `成片工程/`（`styled.ass`→`<单元名>.ass`、`study.srt`→`<单元名>.srt`，保留 `timeline.json`、`顶部提示分行.json`、`章节时间.txt`，清理 `narration.wav`、`layout-reference.mp4`、`render.ass`、`images.ffconcat`、`抽帧核验/` 及未被引用的废图/废音），保证 `课文视频输出/<单元名及主题>/` 仅保留 MP4、Word、PDF 三件套。如需制作抖音 / B站 / YouTube 投稿发布包，可搭配本地项目中的 `lesson-video-publish` 技能（如已安装）。
