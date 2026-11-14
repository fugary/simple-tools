import fs from "fs";
import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);

const macChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
if (process.platform === "darwin" && fs.existsSync(macChrome)) {
  Config.setBrowserExecutable(macChrome);
}

