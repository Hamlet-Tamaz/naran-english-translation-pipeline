import { NextRequest, NextResponse } from "next/server";

// GET-triggerable pipeline runner — same logic as /api/trigger but callable
// via GET (for environments that can only fetch URLs).
// Usage: /api/run?key=<dashboard password>&filename=<file>&robustness=<level>
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const key = searchParams.get("key");
  const filename = searchParams.get("filename");
  const robustness = searchParams.get("robustness") || "standard";

  if (key !== "translathor888") {
    return NextResponse.json({ message: "Invalid key" }, { status: 401 });
  }
  if (!filename) {
    return NextResponse.json({ message: "No filename provided" }, { status: 400 });
  }

  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return NextResponse.json({ message: "GITHUB_TOKEN not configured" }, { status: 500 });
  }

  const repo = "Hamlet-Tamaz/naran-english-translation-pipeline";
  const url = `https://api.github.com/repos/${repo}/actions/workflows/process-video.yml/dispatches`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `token ${token}`,
      Accept: "application/vnd.github.v3+json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ref: "main",
      inputs: { video_filename: filename, robustness },
    }),
  });

  if (response.status === 204) {
    return NextResponse.json({ message: `Pipeline triggered: ${filename} [${robustness}]` });
  }
  const data = await response.json().catch(() => ({}));
  return NextResponse.json({ message: data.message || "Trigger failed" }, { status: response.status });
}
