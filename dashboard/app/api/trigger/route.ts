import { NextResponse } from "next/server";

export async function POST(req: Request) {
  try {
    const { filename, robustness = "standard" } = await req.json();
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
        inputs: {
          video_filename: filename,
          robustness: robustness,
        },
      }),
    });

    if (response.status === 204) {
      return NextResponse.json({ message: `Pipeline triggered [${robustness}]` });
    }
    const data = await response.json();
    return NextResponse.json({ message: data.message || "Trigger failed" }, { status: response.status });
  } catch (e: any) {
    return NextResponse.json({ message: `Error: ${e.message}` }, { status: 500 });
  }
}
