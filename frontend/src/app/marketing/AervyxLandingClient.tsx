"use client";

import { useEffect } from "react";

type Props = {
  bodyHtml: string;
  cssText: string;
};

export function AervyxLandingClient({ bodyHtml, cssText }: Props) {
  useEffect(() => {
    const gliderHost = document.getElementById("gliders");
    if (gliderHost && !gliderHost.dataset.initialized) {
      gliderHost.dataset.initialized = "true";
      [
        { l: "2%", t: "55%", tx: "520px", ty: "-210px", d: 14, dl: 0 },
        { l: "8%", t: "72%", tx: "600px", ty: "-270px", d: 18, dl: -3.5 },
        { l: "0%", t: "45%", tx: "440px", ty: "-185px", d: 16, dl: -7 },
        { l: "18%", t: "78%", tx: "700px", ty: "-310px", d: 21, dl: -5 },
        { l: "4%", t: "85%", tx: "350px", ty: "-160px", d: 12, dl: -10 },
        { l: "12%", t: "62%", tx: "580px", ty: "-240px", d: 23, dl: -2 },
      ].forEach((point) => {
        const dot = document.createElement("div");
        dot.className = "gd";
        dot.style.left = point.l;
        dot.style.top = point.t;
        dot.style.setProperty("--tx", point.tx);
        dot.style.setProperty("--ty", point.ty);
        dot.style.setProperty("--dur", `${point.d}s`);
        dot.style.setProperty("--del", `${point.dl}s`);
        gliderHost.appendChild(dot);
      });
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("in");
          }
        });
      },
      { threshold: 0.1 },
    );
    document.querySelectorAll(".reveal").forEach((element) => observer.observe(element));

    const tabListeners = Array.from(document.querySelectorAll(".sc-tab")).map((tab) => {
      const handler = () => {
        tab.parentElement?.querySelectorAll(".sc-tab").forEach((peer) => peer.classList.remove("active"));
        tab.classList.add("active");
      };
      tab.addEventListener("click", handler);
      return { tab, handler };
    });

    const signupHost = document.querySelector(".su-form") as HTMLElement | null;
    const submitButton = signupHost?.querySelector("[data-signup-submit='true']") as HTMLButtonElement | null;
    const defaultLabel = submitButton?.textContent ?? "Request early access →";

    const handleSubmit = async () => {
      if (!signupHost || !submitButton) return;
      const getValue = (name: string) => (signupHost.querySelector(`[name='${name}']`) as HTMLInputElement | HTMLSelectElement | null)?.value?.trim() ?? "";
      const payload = {
        name: `${getValue("first_name")} ${getValue("last_name")}`.trim(),
        email: getValue("email"),
        org: getValue("org"),
        role: getValue("role"),
        discipline: getValue("discipline"),
        deployment_preference: getValue("deployment_preference"),
      };
      if (!payload.name || !payload.email) {
        window.alert("Please enter your name and email.");
        return;
      }

      submitButton.disabled = true;
      submitButton.textContent = "Submitting…";
      try {
        const response = await fetch("/api/signup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) throw new Error("Signup failed");
        submitButton.textContent = "✓ You're on the list — we'll be in touch!";
        submitButton.style.background = "#00e676";
        submitButton.style.color = "#06090f";
      } catch {
        submitButton.disabled = false;
        submitButton.textContent = defaultLabel;
        window.alert("We couldn't submit your request right now. Please try again.");
      }
    };

    submitButton?.addEventListener("click", handleSubmit);

    return () => {
      observer.disconnect();
      tabListeners.forEach(({ tab, handler }) => tab.removeEventListener("click", handler));
      submitButton?.removeEventListener("click", handleSubmit);
    };
  }, []);

  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: cssText }} />
      <div dangerouslySetInnerHTML={{ __html: bodyHtml }} />
    </>
  );
}
