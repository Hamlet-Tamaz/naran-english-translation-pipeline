import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const checks = {
    github_token: !!process.env.GITHUB_TOKEN,
    kimi_key: !!process.env.KIMI_API_KEY,
    openai_key: !!process.env.OPENAI_API_KEY,
    r2_account_id: !!process.env.R2_ACCOUNT_ID,
    r2_access_key: !!process.env.R2_ACCESS_KEY_ID,
    r2_secret: !!process.env.R2_SECRET_ACCESS_KEY,
    r2_bucket: !!process.env.R2_BUCKET_NAME,
    r2_public_url: !!process.env.R2_PUBLIC_URL,
  };

  const allR2 = checks.r2_account_id && checks.r2_access_key && checks.r2_secret && checks.r2_bucket && checks.r2_public_url;
  const hasTranslator = checks.kimi_key || checks.openai_key;

  return NextResponse.json({
    ready: checks.github_token && hasTranslator,
    github_ready: checks.github_token,
    kimi_ready: checks.kimi_key,
    openai_ready: checks.openai_key,
    translator_ready: hasTranslator,
    r2_ready: allR2,
    checks,
  });
}
