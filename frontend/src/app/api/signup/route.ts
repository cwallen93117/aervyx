import fs from "node:fs";
import path from "node:path";
import { DatabaseSync } from "node:sqlite";
import { NextResponse } from "next/server";

type SignupPayload = {
  name?: string;
  email?: string;
  org?: string;
  role?: string;
  discipline?: string;
  deployment_preference?: string;
};

let database: DatabaseSync | null = null;

function getDatabase() {
  if (!database) {
    const dataDir = path.join(process.cwd(), ".data");
    fs.mkdirSync(dataDir, { recursive: true });
    database = new DatabaseSync(path.join(dataDir, "marketing-signups.db"));
  }
  return database;
}

async function ensureTable() {
  getDatabase().exec(`
    CREATE TABLE IF NOT EXISTS early_access_signups (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      email TEXT NOT NULL,
      org TEXT,
      role TEXT,
      discipline TEXT,
      deployment_preference TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
  `);
}

export async function POST(request: Request) {
  try {
    const payload = (await request.json()) as SignupPayload;
    if (!payload.name || !payload.email) {
      return NextResponse.json({ error: "Name and email are required." }, { status: 400 });
    }
    await ensureTable();
    getDatabase()
      .prepare(
        `INSERT INTO early_access_signups (name, email, org, role, discipline, deployment_preference)
         VALUES (?, ?, ?, ?, ?, ?)`,
      )
      .run(
        payload.name,
        payload.email,
        payload.org ?? null,
        payload.role ?? null,
        payload.discipline ?? null,
        payload.deployment_preference ?? null,
      );
    return NextResponse.json({ ok: true });
  } catch (error) {
    console.error("Failed to store signup", error);
    return NextResponse.json({ error: "Unable to store signup." }, { status: 500 });
  }
}
