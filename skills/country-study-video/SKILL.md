---
name: country-study-video
description: 给定一个或多个国家名，制作小学高年级至初中适用（默认六年级起步）的英语国家介绍双语学习视频与配套讲义，含两轮事实/标注复审冻结门禁、逐句英文配音、零版权合规配图、互动问答和片尾复习。也可从已有英文或中英稿续做。
---

# 国家介绍双语学习视频

只给国名即可开始。给定多个国家时每国独立成集。先在用户指定的工程或当前工作区查找 `国家介绍视频制作/`（兼容历史旧工程的 `国家介绍/`），如有则读取其中的 `AGENTS.md`、`默认配音.json` 和一个已完成篇目。新工程直接采用随技能携带的样式和声音。沿用本次要求及当前工程设置。已有同国工程时，核对稿件、音频和成片，复用仍匹配的材料。

## 目录与交付约定

- **制作工程目录**：`国家介绍视频制作/<两位编号> <中文国名>（<英文国名>）/`（若接手旧工程，兼容识别 `国家介绍/<国名>/Lily自然声版/`）
  - 单集根目录保留：`<国名>介绍中英文学习稿.md`、`lesson.json`（内部使用相对路径）、`front_matter.json`、`分镜.json`、`复习主题.json`、`同页对照.json`、`配图来源.md`（供 `audit_country_assets.py` 校验）
  - 四个子目录：`配图/`（1920×1080 场景图、`sources.json`、`flag_badge.png` 及本地官方国旗 `.svg`）、`配音/`（仅留 `lesson.json` 实际引用的英文 WAV）、`成片工程/`（成片验收后清理 `stage_frames/`、`layout-reference.mp4`、`narration.wav`、`render.ass`、`images.ffconcat`、`study.ass`、`manifest.json`、`scenes.json`、`study.style.json`、`mobile-style.json`、`study.validation.json`，并将 `styled.ass`→`<编号> <中文国名>（<英文国名>）.ass`、`study.srt`→`<编号> <中文国名>（<英文国名>）.srt`，仅保留这 2 份字幕与 `timeline.json`、`timing.json`、`overlay_plan.json` 共 5 个核心轻量文件）、`开发记录/`（统一归档 `成片验证.json`、`逐句语音核查.json` 等过程留痕；已被 `lesson.json` 取代的早期初稿不再留存）
  - 跨集说明与审校汇总统一收入 `国家介绍视频制作/汇总记录/`；共用音色、缓存与工具位于 `配音设置/`、`配音缓存/`、`制作工具/`。
- **最终交付目录**：`国家介绍视频输出/<两位编号> <中文国名>（<英文国名>）/`（与制作目录同名镜像，仅放三件成品，制作目录不另保留 `.docx`/`.pdf`/`.mp4` 副本）：
  - `<编号> <中文国名>（<英文国名>）.mp4`
  - `<编号> <中文国名>（<英文国名>） 双语学习讲义（打印版）.docx`
  - `<编号> <中文国名>（<英文国名>） 双语学习讲义（打印版）.pdf`

1. **规划主线与单一真源母稿（第 1 轮核查：全部事实、史实、教学价值与难度水平）。** 从地理定位和首都切入，用一个孩子能回答的问题串起自然、国旗、文化与生活。**默认至少经两轮事实核查**：第 1 轮须逐项查证全部地理数据、历史年代、文化史实、国旗形制与“最/唯一/第几”等比较范围，保证均有官方地理、权威百科、博物馆或世界遗产等可靠来源依据；同时确保英语语法地道准确、具备真实教学价值，且语言表达、词汇与句型满足**小学高年级至初中生**水平（控制单句长度，避免过密从句）。已有教材时保留学习目标，发现疑点先核实并同步修正正文与复习段。优先用单一真源结构化数据同步维护：国家小档案（`facts`）、首页代表表达速查（`quick_refs`）、核心难词表（`vocab_table`，含美式音标 IPA 与词性）、章节映射（`chapter_map`）、同页对照组（`same_page_groups`）、分镜与 `cues`。
2. **编写逐句双语稿与 V2 讲义，并完成第 2 轮标注/词句深度复审。** 写入 `国家介绍视频制作/<两位编号> <中文国名>（<英文国名>）/<国名>介绍中英文学习稿.md`。结构依次为双语片名与开场、地理与自然、首都与国旗、奇观或标志人文、生活/美食/生态、互动问答、按主题复习的信息卡，以及固定结束语 “Thanks for exploring with us. See you next time!”。省略课堂分组自报。默认调用同级[英语文章教学优化技能](../bilingual-article-teaching/SKILL.md)审稿，并在本步执行**第 2 轮全方位精修**：
   - **地理/历史/文化复核与孩子视角通读**：再次交叉核对第 1 轮确立的数据与比较范围表述无滑坡；孩子可能读不懂的术语、文化专名、语法转折全部补上直白、无歧义的顶部提示（遮住译文复述检验）。
   - **难词音标词性统一与解释到位**：全部核心难词统一在首页词表及正文**首次出现句的 `notes`** 中标明**美式音标 `/.../`、词性与句中义**。
   - **英中、高亮与提示逐条核对**：重点检查固定词组/短语是否完整（严禁截断在 `is located`、`borders with` 或孤立冠词/介词上）、**地理/历史/工程等复合专名是否完整整段高亮**（如 `Trans-Siberian Railway`、`Scandinavian Peninsula`，禁止只标其中半个词）、同一句多处高亮在英文与中文之间是否各自一一对应且顶部解释清楚到位。
   - **复习卡首句须读出主题**：`Review | <Topic>` 每张主题卡片的第一条配音台词必须读出该卡片的主题或对象名称（优先像景点/动物/美食卡那样先独立读出标题词条，或以包含明确主语的完整句开头），严禁仅靠左上角视觉标签而直接用 `Located in...`、`One of the most...`、`The national...`、`A traditional...` 等无主语短语开头，防止只听配音时误以为续接上一张卡片。
3. **定稿硬门禁：脚本强制校验 + Word/PDF 讲义核验全部通过后冻结文本。** 先准备定稿首页元数据（`front_matter.json`，含 `kicker`/`title`/`subtitle`/`header`/`facts`/`quick_refs`/`vocab_table`/`chapter_map`）与洁净清单（`lesson.json`、`分镜.json`、`复习主题.json`、`同页对照.json`），直接调用 `../bilingual-article-teaching/scripts/study_cues.py` 导出正式打印版 `.docx` 并完成校验，严格依次执行以下两道硬核查：
   - 运行 `../bilingual-article-teaching/scripts/study_cues.py lesson.json --strict --front-matter front_matter.json --groups 同页对照.json --check-narration --word "国家介绍视频输出/<两位编号> <中文国名>（<英文国名>）/<两位编号> <中文国名>（<英文国名>） 双语学习讲义（打印版）.docx"`（如已有成片时间线可追加 `--timeline 成片工程/timeline.json`；`study_cues.py --word --front-matter` 已内置新加坡 V2 蓝红讲义样式，`<100` 条自动两位编号与 `0.85 cm` 悬挂缩进，`>=100` 条自动三位编号与 `0.95 cm` 缩进，禁止另行手写 Word 生成脚本），确认 0 错误，并对脚本列出的所有多高亮句与超长句完成人工确认；
   - 运行 `../bilingual-article-teaching/scripts/verify_pdf_handout.py ... --export-from ... --cues lesson.json --groups 同页对照.json --expect-front-pages 1 --no-single-cue-tail --require-ipa`（macOS 下由 Word 导出同名最新 PDF），确认中文编码完整、无康熙部首乱码、首页未溢出、末页无单条孤儿、全集条目与同页分组 100% 对位。
   - **前置冻结闸门**：必须确认第 1–3 步以上全部文字、史实、标注与打印讲义确认无误并**冻结文本内容**后，才允许进入后续配音、配图合成与视频渲染操作；若后续发现文字需修订，必须回到本步骤重审、重导讲义并重新冻结，严禁带着未定稿或有错讲义进入配音与渲染。
4. **按“零版权 + 史实防错”选图并构建国旗叠加层。** 配图严格遵循四条铁律（详见[配图来源与无版权选图规范](references/image-sourcing.md)）：
   - **地理不画手绘地图**：凡地理方位、山地海域一律采用可考证的自然景观实景摄影，禁用易错手绘地图。
   - **官方矢量国旗独立层**：调用 `scripts/make_flag_badge.py`（传本地 `--input path/to/flag.svg` 或 `--download-flag Flag_of_<Country>.svg --save-svg 配图/<中文国名>_Flag_of_<Country>.svg`）基于官方矢量 SVG 源码栅格化为圆角深色描边 `配图/flag_badge.png`（默认宽 `296px`，不超过画面 16%），仅在讲读国旗 Cue 期间通过 `lesson.json` 的 `overlays` 叠加在右上安全区。
   - **严格零版权选图**：默认只接受 **AI 原创生成** 或原生 **`CC0 1.0` / `Public Domain` / `Public Domain (NASA)`**（Wikimedia Commons 核验、WordPress Photo Directory、NASA 图库）；禁用 `Unsplash` / `Pixabay` / `Pexels` 及任何 `CC BY` / `CC BY-SA` / `NC` / `ND` / `FAL` 素材。如遇 AI 配额限额，把稀缺创意图留给 AI，其余运行 `scripts/search_cc0_images.py search` 生成 Contact Sheet 网格目视筛选后，再用 `scripts/search_cc0_images.py fetch --crop-y ...` 裁切归一化为 `1920×1080` RGB 并自动登记到 `配图/sources.json`。
   - **一题一图互动配图 + 轻量化防剧透 & 溯源闭环**：每道互动题默认按题干对象选用一张**无字横图**，从提问、3.5 秒停顿到答句结束全程共用同一张画面，文字答案随答句出现；仅对两类会“看图即直出答案”的题留保护——（1）**国旗配色回忆题**以该国风景为底图，提问与 3.5 秒停顿不叠 `flag_badge.png`，到答句再叠出官方国旗角标；（2）**单一实物特写猜名题**（图上只有一个直指答案单词的近景特写）可用安静环境/远景图过渡到答句特写，或改从数量/特征/原因角度设问。辨色/计数/特征观察题从提问起即展示观察对象。写入 `配图/sources.json` 并运行 `scripts/write_country_sources.py` 与 `scripts/audit_country_assets.py` 校验 `配图来源.md` 和磁盘 SHA-256 一致。
5. **生成英文配音、Whisper ASR 体检与动态避让渲染。** 确认文本冻结后逐句生成英文配音（可用 `spoken` 指定年份、小数与外文地名精确读音），默认调用 `lesson_media.py narrate`（配置见[声音配置](../teaching-slideshow-video/assets/lily.json)，多集共用同一系列 `--cache` 去重，普通句停顿 2 秒、互动题 `pause: 3.5`，片尾使用[系列结束语](assets/lily-outro.wav)或工程共用 `Lily 系列结束语.wav`）。配音完成后运行 `../teaching-slideshow-video/scripts/audit_narration.py --manifest lesson.json` 检查物理电平与本地 `mlx-whisper` 相似度（低分项、句首带停顿的短引导词与专有名词局部切片复听，仅可微调 `spoken` 重录，不得更改已冻结字幕原文）。随后依次运行 `lesson_media.py prepare`、`build_subtitles.py --font-zh "Heiti SC" --font-en "Arial"`（沿用系列固定中英文字体）、`scripts/format_country_subtitles.py --build 成片工程 --review-topics 复习主题.json --ffmpeg FFmpeg路径`（已原生接管顶部 10% 磨砂学习底板与 22% 高度 `ReviewTopic` 条，新做单集无需额外再调用旧 `顶部学习提示.py`），最后用 `lesson_media.py render` 完成 `stage_frames/` 预归一化、`StudyHintPlate` 碰撞避让国旗叠加及临时文件解码通过后再原子发布。
6. **多端成品验收、讲义时间回填与镜像交付。** 
   - **前置素材零缺陷与成片轻量验收**：因为底层排版（底部字幕字号与间距公式、顶部提示避让气泡、右上角国旗独立徽章、逐句 PCM/AAC 拼接）全部由数学与样式规则确定，且由前置 `audit_country_assets.py`（无版权配图与 SVG 徽章 0 问题）与 `study_cues.py --strict`（字幕、音标与 0 拆组 0 错误）双重硬门禁锁死，**日常交付无需重复执行耗时占显存的抽帧拼图（`_grid.jpg`、`_mobile480p.jpg`）与多模态大图读入**。直接通过 `lesson_media.py` 生成的 `verification.json` 或轻量 `ffprobe`（核验 1080p/30fps/AAC 码流存在、时长与 `timeline.json` 一致、无坏帧）即可毫秒级完成成片验收；若历史渲染的成片与当前台词、配音和分镜完全一致且流完整，直接复用成片并回填时间戳，避免不必要的重复完整转码。
   - **讲义时间回填与闭环校验**：出片并获得 `成片工程/timeline.json` 后，用 `study_cues.py ... --timeline 成片工程/timeline.json --word ...` 与 `verify_pdf_handout.py --export-from ...` 刷新终版 Word/PDF（在章节标题右侧标注实测 `成片 MM:SS`）并复验分页（确保 0 拆组、无康熙部首乱码）。
   - **工程瘦身与三件套交付**：将 `.verification.json` 归入 `开发记录/成片验证.json`，按目录约定精简 `成片工程/`（重命名 `<编号> <中文国名>（<英文国名>）.ass/.srt` 并仅留上述 5 个轻量文件），清理临时抽帧与缓存；确认 `国家介绍视频输出/<两位编号> <中文国名>（<英文国名>）/` 仅保留终版 `.mp4` 与 `双语学习讲义（打印版）.docx/.pdf` 镜像三件套，不残留独立于该目录外的旧版散落文件。

复习主题文件内容形如 `[{"cue": 12, "topic": "River Valley"}]`。cue 是从 0 起的正文清单下标，按出现顺序填写，最后一条朗读留给结束语。时间取自本集时间轴。第一句英文按「国名 — 主题」拆成封面两行，中文作为第三行。复习标签固定在画面高度 22%。只有封面时传空数组文件。交付用最终 ASS 和基础步骤生成的 SRT。
