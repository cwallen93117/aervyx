import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

export default async function DashboardLayout({ children }: { children: ReactNode }) {
  const cookieStore = await cookies();
  if (!cookieStore.has("flightcomp_session")) {
    redirect("/login?next=/dashboard");
  }

  return children;
}
