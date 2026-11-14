import React from "react";
import { Composition } from "remotion";
import { StudyVideo } from "./StudyVideo";
import projectDataRaw from "./data/project.json";
import { StudyProjectData } from "./types";

const projectData = projectDataRaw as StudyProjectData;

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="StudyVideo"
      component={StudyVideo}
      durationInFrames={Math.max(1, projectData.meta.durationInFrames)}
      fps={projectData.meta.fps}
      width={projectData.meta.width}
      height={projectData.meta.height}
      defaultProps={{
        project: projectData,
      }}
    />
  );
};
