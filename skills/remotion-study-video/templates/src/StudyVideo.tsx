import React from "react";
import { AbsoluteFill, Audio, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { StudyProjectData } from "./types";
import { SceneLayer } from "./components/SceneLayer";
import { GraphicOverlays } from "./components/GraphicOverlays";
import { HudLayer } from "./components/HudLayer";
import { TopChrome } from "./components/TopChrome";
import { SubtitleLayer } from "./components/SubtitleLayer";

export type StudyVideoProps = {
  project: StudyProjectData;
};

export const StudyVideo: React.FC<StudyVideoProps> = ({ project }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;

  const activeCue =
    project.cues.find((c) => currentTime >= c.start && currentTime < c.end) ?? null;

  const hasTopNote = Boolean(
    (activeCue?.richNotes && activeCue.richNotes.length > 0) ||
      (activeCue?.notes && activeCue.notes.length > 0)
  );
  const overlays = project.overlays ?? [];
  const hasActiveCoverHero = overlays.some(
    (o) => o.kind === "cover_hero" && currentTime >= o.start && currentTime < o.end
  );

  return (
    <AbsoluteFill style={{ backgroundColor: "#090d16", overflow: "hidden" }}>
      {project.meta.audioFile ? (
        <Audio src={staticFile(project.meta.audioFile)} />
      ) : null}

      <SceneLayer
        scenes={project.scenes}
        spotlights={project.spotlights ?? []}
      />

      <GraphicOverlays overlays={overlays} hasTopNote={hasTopNote} />

      <HudLayer hudItems={project.hud ?? []} hasTopNote={hasTopNote} />

      <TopChrome
        activeCue={activeCue}
        totalDuration={project.meta.durationInSeconds}
        defaultChapter={project.meta.subtitle}
      />

      <SubtitleLayer activeCue={activeCue} isCoverCue={hasActiveCoverHero} />
    </AbsoluteFill>
  );
};
