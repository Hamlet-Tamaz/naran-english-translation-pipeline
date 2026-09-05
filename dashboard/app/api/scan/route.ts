import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return NextResponse.json({ message: "GITHUB_TOKEN not configured" }, { status: 500 });
  }

  try {
    const res = await fetch(
      `https://api.github.com/repos/Hamlet-Tamaz/naran-english-translation-pipeline/actions/workflows/scan-incoming.yml/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github.v3+json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ref: "main" }),
      }
    );

    if (res.status === 204) {
      return NextResponse.json({ message: "Scan triggered! Check GitHub Actions." });
    }
    const err = await res.text();
    return NextResponse.json({ message: `GitHub error: ${err}` }, { status: res.status });
  } catch (e: any) {
    return NextResponse.json({ message: e.message }, { status: 500 });
  }
}
