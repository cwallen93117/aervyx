import { NextResponse } from "next/server";
import { Pool } from "pg";

type SignupPayload = {
  name?: string;
  email?: string;
  org?: string;
  role?: string;
  discipline?: string;
  deployment_preference?: string;
};

let pool: Pool | null = null;

function databaseUrl() {
  const raw = process.env.DATABASE_URL ?? process.env.SIGNUP_DATABASE_URL;
  if (!raw) {
    throw new Error("DATABASE_URL is not configured for signup storage");
  }
  return raw.replace("postgresql+psycopg://", "postgresql://");
}

function getPool() {
  if (!pool) {
    pool = new Pool({ connectionString: databaseUrl() });
  }
  return pool;
}

async function ensureTable() {
  await getPool().query(`
    CREATE TABLE IF NOT EXISTS early_access_signups (
      id BIGSERIAL PRIMARY KEY,
      name TEXT NOT NULL,
      email TEXT NOT NULL,
      org TEXT,
      role TEXT,
      discipline TEXT,
      deployment_preference TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
    await getPool().query(
      `INSERT INTO early_access_signups (name, email, org, role, discipline, deployment_preference)
       VALUES ($1, $2, $3, $4, $5, $6)`,
      [
        payload.name,
        payload.email,
        payload.org ?? null,
        payload.role ?? null,
        payload.discipline ?? null,
        payload.deployment_preference ?? null,
      ],
    );
    return NextResponse.json({ ok: true });
  } catch (error) {
    console.error("Failed to store signup", error);
    return NextResponse.json({ error: "Unable to store signup." }, { status: 500 });
  }
}
