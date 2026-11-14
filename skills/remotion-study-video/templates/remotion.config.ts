import fs from "fs";
import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
// 2s GOP (at 30fps) keeps initial MP4 size lean while enabling fast FFmpeg GOP-aligned partial patching
Config.setGopSize(60);

const macChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
if (process.platform === "darwin" && fs.existsSync(macChrome)) {
  Config.setBrowserExecutable(macChrome);
}

