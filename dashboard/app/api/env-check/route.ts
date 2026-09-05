import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  const checks = {
    github_token: !!process.env.GITHUB_TOKEN,
    r2_account_id: !!process.env.R2_ACCOUNT_ID,
    r2_access_key: !!process.env.R2_ACCESS_KEY_ID,
    r2_secret: !!process.env.R2_SECRET_ACCESS_KEY,
    r2_bucket: !!process.env.R2_BUCKET_NAME,
    r2_public_url: !!process.env.R2_PUBLIC_URL,
  };

  const allR2 = checks.r2_account_id && checks.r2_access_key && checks.r2_secret && checks.r2_bucket && checks.r2_public_url;

  return NextResponse.json({
    ready: checks.github_token && allR2,
    github_ready: checks.github_token,
    r2_ready: allR2,
    checks,
  });
}
