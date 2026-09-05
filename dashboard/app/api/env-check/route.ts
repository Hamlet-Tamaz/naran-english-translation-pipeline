import { NextResponse } from "next/server";

export async function GET() {
  const checks = {
    GITHUB_TOKEN: !!process.env.GITHUB_TOKEN,
    R2_ACCOUNT_ID: !!process.env.R2_ACCOUNT_ID,
    R2_ACCESS_KEY_ID: !!process.env.R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY: !!process.env.R2_SECRET_ACCESS_KEY,
    R2_BUCKET_NAME: !!process.env.R2_BUCKET_NAME,
    R2_PUBLIC_URL: !!process.env.R2_PUBLIC_URL,
    OPENAI_API_KEY: !!process.env.OPENAI_API_KEY,
    HF_TOKEN: !!process.env.HF_TOKEN,
  };

  const github_ready = checks.GITHUB_TOKEN;
  const r2_ready = checks.R2_ACCOUNT_ID && checks.R2_ACCESS_KEY_ID && checks.R2_SECRET_ACCESS_KEY && checks.R2_BUCKET_NAME && checks.R2_PUBLIC_URL;
  const openai_ready = checks.OPENAI_API_KEY;

  return NextResponse.json({
    ready: github_ready && openai_ready,
    github_ready,
    r2_ready,
    openai_ready,
    checks,
  });
}
