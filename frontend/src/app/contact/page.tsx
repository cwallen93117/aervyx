import type { Metadata } from "next";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import nodemailer from "nodemailer";
import "../marketing/aervyx-landing.css";

export const metadata: Metadata = { title: "Contact — Aervyx" };

const CONTACT_EMAIL = "aervyxnet@gmail.com";
const recentSubmissions = new Map<string, number>();

function field(formData: FormData, name: string, maxLength: number) {
  return String(formData.get(name) ?? "").trim().slice(0, maxLength);
}

async function sendContact(formData: FormData) {
  "use server";

  const name = field(formData, "name", 120);
  const email = field(formData, "email", 254);
  const subject = field(formData, "subject", 160).replace(/[\r\n]+/g, " ");
  const message = field(formData, "message", 5000);
  if (!name || !subject || !message || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    redirect("/contact?error=invalid");
  }

  const requestHeaders = await headers();
  const clientIp = requestHeaders.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";
  const now = Date.now();
  // ponytail: process-local throttle is enough for one frontend container; use a shared store if the service scales out.
  if (now - (recentSubmissions.get(clientIp) ?? 0) < 60_000) redirect("/contact?error=rate");
  recentSubmissions.set(clientIp, now);

  const password = process.env.GMAIL_APP_PASSWORD;
  if (!password) {
    console.error("Contact form unavailable: GMAIL_APP_PASSWORD is not configured");
    redirect("/contact?error=unavailable");
  }

  try {
    await nodemailer
      .createTransport({
        service: "gmail",
        auth: { user: CONTACT_EMAIL, pass: password },
      })
      .sendMail({
        from: `Aervyx Website <${CONTACT_EMAIL}>`,
        to: CONTACT_EMAIL,
        replyTo: { name, address: email },
        subject: `Aervyx website contact: ${subject}`,
        text: `Name: ${name}\nEmail: ${email}\n\n${message}`,
      });
  } catch (error) {
    console.error("Contact email failed", error);
    redirect("/contact?error=send");
  }

  redirect("/contact?sent=1");
}

type ContactPageProps = {
  searchParams: Promise<{ error?: string; sent?: string }>;
};

export default async function ContactPage({ searchParams }: ContactPageProps) {
  const status = await searchParams;
  const errorMessage = {
    invalid: "Please complete every field with a valid email address.",
    rate: "Please wait a minute before sending another message.",
    unavailable: "Email is temporarily unavailable. Please try again later.",
    send: "Your message could not be sent. Please try again.",
  }[status.error ?? ""];

  return (
    <main className="contact-page">
      <section className="contact-card">
        <a href="/" className="contact-back">&larr; Aervyx<span>.net</span></a>
        <div className="eyebrow">Contact</div>
        <h1>How can we help?</h1>
        <p className="contact-lede">Questions, feedback, and support requests are welcome.</p>

        {status.sent === "1" ? <p className="contact-status success" role="status">Your message was sent. We&apos;ll be in touch.</p> : null}
        {errorMessage ? <p className="contact-status error" role="alert">{errorMessage}</p> : null}

        <form action={sendContact} className="su-form">
          <label>
            <span className="sf-lbl">Name</span>
            <input className="sf-in" name="name" autoComplete="name" maxLength={120} required />
          </label>
          <label>
            <span className="sf-lbl">Email</span>
            <input className="sf-in" name="email" type="email" autoComplete="email" maxLength={254} required />
          </label>
          <label>
            <span className="sf-lbl">Subject</span>
            <input className="sf-in" name="subject" maxLength={160} required />
          </label>
          <label>
            <span className="sf-lbl">Message</span>
            <textarea className="sf-in contact-message" name="message" rows={8} maxLength={5000} required />
          </label>
          <button className="sf-submit" type="submit">Send message</button>
        </form>
      </section>
    </main>
  );
}
