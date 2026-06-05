import { notFound } from "next/navigation";

import ReplayMemoryProfilerClient from "./ReplayMemoryProfilerClient";

export default function ReplayMemoryProfilerPage() {
  if (process.env.NODE_ENV === "production") {
    notFound();
  }
  return <ReplayMemoryProfilerClient />;
}
