import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const { filename } = await req.json();
  const token = process.env.GITHUB_TOKEN;
  const owner = "Hamlet-Tamaz";
  const repo = "naran-english-translation-pipeline";

  if (!token) {
    return NextResponse.json({ message: "GITHUB_TOKEN not configured" }, { status: 500 });
  }

  try {
    const res = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/actions/workflows/process-video.yml/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github.v3+json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ref: "main",
          inputs: { video_filename: filename },
        }),
      }
    );

    if (res.status === 204) {
      return NextResponse.json({ message: "Pipeline triggered! Check GitHub Actions." });
    }
    const err = await res.text();
    return NextResponse.json({ message: `GitHub error: ${err}` }, { status: res.status });
  } catch (e: any) {
    return NextResponse.json({ message: `Error: ${e.message}` }, { status: 500 });
  }
}
