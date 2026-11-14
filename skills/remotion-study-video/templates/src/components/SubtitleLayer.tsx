import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { CueItem, RichTextSegment } from "../types";

interface SubtitleLayerProps {
  activeCue: CueItem | null;
  isCoverCue: boolean;
}

function renderRichSegments(
  segments: RichTextSegment[],
  baseColor: string,
  highlightColor: string
): React.ReactNode {
  return segments.map((seg, idx) => (
    <span
      key={idx}
      style={{
        color: seg.highlight ? highlightColor : baseColor,
        fontWeight: 800,
      }}
    >
      {seg.text}
    </span>
  ));
}

function renderHighlightedText(
  text: string,
  highlights: string[] | undefined,
  baseColor: string,
  highlightColor: string
): React.ReactNode {
  if (!highlights || highlights.length === 0) {
    return text;
  }

  const valid = highlights.filter((h) => h && text.includes(h));
  if (valid.length === 0) {
    return text;
  }

  const escaped = valid
    .slice()
    .sort((a, b) => b.length - a.length)
    .map((h) => h.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const regex = new RegExp(`(${escaped.join("|")})`, "g");
  const parts = text.split(regex);

  return parts.map((part, i) => {
    const isHit = valid.includes(part);
    if (!isHit) {
      return (
        <span key={i} style={{ color: baseColor }}>
          {part}
        </span>
      );
    }
    return (
      <span
        key={i}
        style={{
          color: highlightColor,
          fontWeight: 800,
        }}
      >
        {part}
      </span>
    );
  });
}

export const SubtitleLayer: React.FC<SubtitleLayerProps> = ({
  activeCue,
  isCoverCue,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  if (!activeCue || isCoverCue) {
    return null;
  }

  const fadeIn = interpolate(t, [activeCue.start, activeCue.start + 0.16], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const enLen = activeCue.en.length;
  const zhLen = activeCue.zh.length;
  const enFontSize = enLen > 85 ? 38 : enLen > 62 ? 44 : 52;
  const zhFontSize = zhLen > 38 ? 34 : zhLen > 28 ? 38 : 44;

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {/* Bottom cinema gradient scrim */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: 260,
          background:
            "linear-gradient(to top, rgba(0, 0, 0, 0.78) 0%, rgba(0, 0, 0, 0.45) 50%, rgba(0, 0, 0, 0) 100%)",
        }}
      />

      {/* Bottom bilingual subtitles (bilingual-study-subtitles classic styling) */}
      <div
        style={{
          position: "absolute",
          left: 80,
          right: 80,
          bottom: 42,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          textAlign: "center",
          gap: 8,
          opacity: fadeIn,
        }}
      >
        <div
          style={{
            maxWidth: 1720,
            fontSize: enFontSize,
            lineHeight: 1.28,
            letterSpacing: "0.01em",
            fontWeight: 700,
            fontFamily: "Arial, 'SF Pro Display', sans-serif",
            color: "#FFFFFF",
            WebkitTextStroke: "4px #101820",
            paintOrder: "stroke fill",
            textShadow: "0 3px 10px rgba(0,0,0,0.92)",
            wordBreak: "break-word",
          }}
        >
          {activeCue.richEn && activeCue.richEn.length > 0
            ? renderRichSegments(activeCue.richEn, "#FFFFFF", "#FF7B25")
            : renderHighlightedText(
                activeCue.en,
                activeCue.highlightEn,
                "#FFFFFF",
                "#FF7B25"
              )}
        </div>
        <div
          style={{
            maxWidth: 1720,
            fontSize: zhFontSize,
            lineHeight: 1.3,
            letterSpacing: "0.03em",
            fontWeight: 700,
            fontFamily: "'Heiti SC', 'PingFang SC', system-ui, sans-serif",
            color: "#FFBC00",
            WebkitTextStroke: "3.5px #101820",
            paintOrder: "stroke fill",
            textShadow: "0 3px 10px rgba(0,0,0,0.92)",
            wordBreak: "break-word",
          }}
        >
          {activeCue.richZh && activeCue.richZh.length > 0
            ? renderRichSegments(activeCue.richZh, "#FFBC00", "#FF7B25")
            : renderHighlightedText(
                activeCue.zh,
                activeCue.highlightZh,
                "#FFBC00",
                "#FF7B25"
              )}
        </div>
      </div>
    </AbsoluteFill>
  );
};
