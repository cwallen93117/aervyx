import type { Metadata } from "next";
import { LiveWatchClient } from "./LiveWatchClient";

export const metadata: Metadata = {
  title: "Watch Live — Aervyx",
  description: "Watch live tracking for hang gliding and paragliding competitions",
};

export default function LivePage() {
  return <LiveWatchClient />;
}
