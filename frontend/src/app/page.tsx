import fs from "node:fs";
import path from "node:path";

import { AervyxLandingClient } from "./marketing/AervyxLandingClient";

function readMarketingFile(name: string) {
  return fs.readFileSync(path.join(process.cwd(), "src", "app", "marketing", name), "utf8");
}

export default function LandingPage() {
  const bodyHtml = readMarketingFile("aervyx-body.html");
  const cssText = readMarketingFile("aervyx-landing.css");

  return <AervyxLandingClient bodyHtml={bodyHtml} cssText={cssText} />;
}
