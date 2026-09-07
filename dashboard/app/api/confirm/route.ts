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
    const { filename, publicUrl, objectKey } = await req.json();
    if (!filename || !publicUrl) {
      return NextResponse.json({ message: "Missing fields" }, { status: 400 });
    }

    const apiHeaders = {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github.v3+json",
      "Content-Type": "application/json",
    };

    // Get current queue.json
    const queueRes = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPO}/contents/queue.json?ref=${BRANCH}`,
      { headers: apiHeaders }
    );

    let queueData: any = { videos: [] };
    let queueSha = "";
    if (queueRes.ok) {
      const queueFile = await queueRes.json();
      queueSha = queueFile.sha;
      queueData = JSON.parse(Buffer.from(queueFile.content, "base64").toString("utf-8"));
    }

    queueData.videos = queueData.videos || [];
    queueData.videos.push({
      filename,
      status: "pending_approval",
      source_url: publicUrl,
      object_key: objectKey,
      uploaded_at: new Date().toISOString(),
      processed_at: null,
    });

    const updateRes = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPO}/contents/queue.json`,
      {
        method: "PUT",
        headers: apiHeaders,
        body: JSON.stringify({
          message: `queue: add ${filename} via R2`,
          content: Buffer.from(JSON.stringify(queueData, null, 2)).toString("base64"),
          branch: BRANCH,
          sha: queueSha || undefined,
        }),
      }
    );

    if (!updateRes.ok) {
      const err = await updateRes.text();
      return NextResponse.json({ message: `Queue update failed: ${err}` }, { status: 500 });
    }

    return NextResponse.json({ message: "Upload confirmed", filename });
  } catch (e: any) {
    return NextResponse.json({ message: e.message }, { status: 500 });
  }
}
