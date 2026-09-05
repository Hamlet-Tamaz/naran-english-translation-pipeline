import { NextRequest, NextResponse } from "next/server";

const OWNER = "Hamlet-Tamaz";
const REPO = "naran-english-translation-pipeline";
const BRANCH = "main";

export async function POST(req: NextRequest) {
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return NextResponse.json({ message: "GITHUB_TOKEN not configured" }, { status: 500 });
  }

  try {
    const { filename } = await req.json();
    if (!filename) {
      return NextResponse.json({ message: "No filename provided" }, { status: 400 });
    }

    const apiHeaders = {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github.v3+json",
      "Content-Type": "application/json",
    };

    // 1. Reset queue.json status to pending_approval
    const queueRes = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPO}/contents/queue.json?ref=${BRANCH}`,
      { headers: apiHeaders }
    );

    let queueData: any = { videos: [] };
    let queueSha = "";
    if (queueRes.ok) {
      const qf = await queueRes.json();
      queueSha = qf.sha;
      queueData = JSON.parse(Buffer.from(qf.content, "base64").toString("utf-8"));
    }

    let found = false;
    for (const v of queueData.videos || []) {
      if (v.filename === filename) {
        v.status = "pending_approval";
        v.processed_at = null;
        found = true;
        break;
      }
    }

    if (!found) {
      return NextResponse.json({ message: "Video not found in queue" }, { status: 404 });
    }

    const updateQueueRes = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPO}/contents/queue.json`,
      {
        method: "PUT",
        headers: apiHeaders,
        body: JSON.stringify({
          message: `queue: reset ${filename} for re-processing`,
          content: Buffer.from(JSON.stringify(queueData, null, 2)).toString("base64"),
          branch: BRANCH,
          sha: queueSha,
        }),
      }
    );

    if (!updateQueueRes.ok) {
      const err = await updateQueueRes.text();
      return NextResponse.json({ message: `Queue update failed: ${err}` }, { status: 500 });
    }

    // 2. Trigger pipeline immediately
    const triggerRes = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/process-video.yml/dispatches`,
      {
        method: "POST",
        headers: apiHeaders,
        body: JSON.stringify({
          ref: BRANCH,
          inputs: { video_filename: filename },
        }),
      }
    );

    if (triggerRes.status === 204) {
      return NextResponse.json({ message: `Re-processing ${filename}! Check GitHub Actions.` });
    }
    const err = await triggerRes.text();
    return NextResponse.json({ message: `Pipeline trigger failed: ${err}` }, { status: triggerRes.status });
  } catch (e: any) {
    return NextResponse.json({ message: e.message }, { status: 500 });
  }
}
