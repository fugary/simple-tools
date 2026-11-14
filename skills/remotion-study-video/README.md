# Remotion Study Video Skill

基于 **Remotion (React + TypeScript)** 的双语教学视频动效合成技能。

## 设计定位

本技能承接上游教研、配图、配音与双语字幕规范产物，**彻底取代 `image-motion` 像素扭曲算法与手写无头 Chrome CDP 截图管线**：

* **保留上游**：继续复用 `bilingual-article-teaching`、`country-study-video` / `textbook-unit-video`、`teaching-slideshow-video`（Lily 配音与 ASR 体检）及 `bilingual-study-subtitles`（语义断行、词汇高亮与提示文案）的产物。
* **废弃淘汰**：不再使用 `image-motion`（避免 2D 网格烟雾与果冻扭曲）和手写 `render_video.mjs` / `render_pipeline.js` 截图循环。
* **低资源高质感**：纯前端矢量动效（React + CSS/SVG + `spring()` 物理缓动）、`@remotion/transitions` 转场、局部聚光聚焦（Spotlight）、以及可选的真实黑底 Screen 混合 `<OffthreadVideo>` 素材叠加，无需重算力 AI 视频生成即可在普通电脑高速出片。

详见 [SKILL.md](SKILL.md)、[references/data-schema.md](references/data-schema.md) 与 [references/design-and-effects.md](references/design-and-effects.md)。
