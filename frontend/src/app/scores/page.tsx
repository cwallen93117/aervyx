import type { Metadata } from "next";
import { PublicScoresClient } from "./PublicScoresClient";

export const metadata: Metadata = {
  title: "Comp Scores - Aervyx",
  description: "View public competition scores and task maps for Aervyx events",
};

export default function ScoresPage() {
  return <PublicScoresClient />;
}
