import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { CueItem, RichTextSegment } from "../types";

interface TopChromeProps {
  activeCue: CueItem | null;
  totalDuration: number;
  defaultChapter?: string;
}

function renderRichNoteLine(segments: RichTextSegment[]): React.ReactNode {
  return segments.map((seg, idx) => (
    <span
      key={idx}
      style={{
        color: seg.highlight ? "#FF7B25" : "#FFFFFF",
        fontWeight: seg.highlight ? 800 : 700,
      }}
    >
      {seg.text}
    </span>
  ));
}

function renderGrammarNote(note: string): React.ReactNode {
  const parts = note.split(/([A-Za-z][A-Za-z0-9\s'’\-+/.,!?]*)/g);
  return parts.map((part, idx) => {
    if (!part) return null;
    const isAscii = /^[A-Za-z]/.test(part);
    return (
      <span
        key={idx}
        style={{
          color: isAscii ? "#FF7B25" : "#FFFFFF",
          fontWeight: isAscii ? 800 : 700,
        }}
      >
        {part}
      </span>
    );
  });
}

export const TopChrome: React.FC<TopChromeProps> = ({
  activeCue,
  totalDuration,
  defaultChapter = "STUDY VIDEO",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const progressPct = Math.max(0, Math.min(100, (t / Math.max(0.1, totalDuration)) * 100));

  const pillLabel = activeCue?.reviewTopic
    ? `Review | ${activeCue.reviewTopic}`
    : activeCue?.chapter || defaultChapter;

  const richNoteLines = activeCue?.richNotes ?? [];
  const plainNoteLines = activeCue?.notes ?? [];
  const hasNotes = richNoteLines.length > 0 || plainNoteLines.length > 0;
  const noteLocalFrame = activeCue ? Math.max(0, Math.round((t - activeCue.start) * fps)) : 0;
  const noteEnter = spring({ frame: noteLocalFrame, fps, config: { damping: 14, stiffness: 130 } });
  const noteExit = activeCue
    ? interpolate(t, [activeCue.end - 0.3, activeCue.end], [1, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 0;

  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {/* Top thin progress track */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 5,
          backgroundColor: "rgba(255, 255, 255, 0.15)",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${progressPct}%`,
            background: "linear-gradient(90deg, #EF4444 0%, #F59E0B 50%, #38BDF8 100%)",
            boxShadow: "0 0 10px rgba(56, 189, 248, 0.6)",
          }}
        />
      </div>

      {/* Top-left Chapter / Review Breadcrumb Pill (safe vertical lane y=24..72) */}
      <div
        style={{
          position: "absolute",
          top: 24,
          left: 64,
          display: "inline-flex",
          alignItems: "center",
          gap: 12,
          padding: "10px 24px",
          borderRadius: 999,
          backgroundColor: "rgba(15, 23, 42, 0.45)",
          border: "1px solid rgba(255, 255, 255, 0.22)",
          backdropFilter: "blur(20px)",
          boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
          color: "#F1F5F9",
          fontSize: 22,
          fontWeight: 600,
          letterSpacing: "0.04em",
          fontFamily: "'SF Pro Display', 'PingFang SC', system-ui, sans-serif",
        }}
      >
        <span
          style={{
            width: 10,
            height: 10,
            borderRadius: "50%",
            backgroundColor: "#F59E0B",
            boxShadow: "0 0 12px #F59E0B",
            display: "inline-block",
          }}
        />
        <span>{pillLabel}</span>
      </div>

      {/* Top-center Study Hint Plate (strictly y=90, below topbar pill so zero collision) */}
      {hasNotes ? (
        <div
          style={{
            position: "absolute",
            top: 90,
            left: "50%",
            width: "max-content",
            transform: `translate(-50%, ${(1 - noteEnter) * -16}px)`,
            opacity: noteEnter * noteExit,
            maxWidth: 1620,
            padding: "14px 36px",
            borderRadius: 22,
            backgroundColor: "rgba(5, 5, 5, 0.72)",
            border: "1px solid rgba(255, 123, 37, 0.35)",
            backdropFilter: "blur(20px)",
            boxShadow: "0 10px 30px rgba(0, 0, 0, 0.45)",
            textAlign: "center",
          }}
        >
          {richNoteLines.length > 0
            ? richNoteLines.map((segments, idx) => {
                const totalLen = segments.reduce((acc, s) => acc + s.text.length, 0);
                return (
                  <div
                    key={idx}
                    style={{
                      fontSize: totalLen > 48 ? 30 : 36,
                      lineHeight: 1.38,
                      fontFamily: "Arial, 'PingFang SC', 'Heiti SC', sans-serif",
                    }}
                  >
                    {renderRichNoteLine(segments)}
                  </div>
                );
              })
            : plainNoteLines.map((note, idx) => (
                <div
                  key={idx}
                  style={{
                    fontSize: note.length > 48 ? 30 : 36,
                    lineHeight: 1.38,
                    fontFamily: "Arial, 'PingFang SC', 'Heiti SC', sans-serif",
                  }}
                >
                  {renderGrammarNote(note)}
                </div>
              ))}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
