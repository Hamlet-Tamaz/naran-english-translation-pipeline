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
    const formData = await req.formData();
    const file = formData.get("file") as File;

    if (!file) {
      return NextResponse.json({ message: "No file provided" }, { status: 400 });
    }

    if (!file.type.startsWith("video/")) {
      return NextResponse.json({ message: "Only video files are allowed" }, { status: 400 });
    }

    if (file.size > 100 * 1024 * 1024) {
      return NextResponse.json(
        { message: "File too large. Max 100MB. Use Git LFS for larger files." },
        { status: 400 }
      );
    }

    const filename = file.name;
    const path = `incoming/${filename}`;

    // Read file and base64 encode
    const bytes = await file.arrayBuffer();
    const base64 = Buffer.from(bytes).toString("base64");

    const apiHeaders = {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github.v3+json",
      "Content-Type": "application/json",
    };

    // Step 1: Upload file to GitHub
    const uploadRes = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPO}/contents/${path}`,
      {
        method: "PUT",
        headers: apiHeaders,
        body: JSON.stringify({
          message: `upload: ${filename}`,
          content: base64,
          branch: BRANCH,
        }),
      }
    );

    if (!uploadRes.ok) {
      const err = await uploadRes.text();
      return NextResponse.json(
        { message: `GitHub upload failed: ${err}` },
        { status: uploadRes.status }
      );
    }

    // Step 2: Update queue.json
    const queueRes = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPO}/contents/queue.json?ref=${BRANCH}`,
      { headers: apiHeaders }
    );

    let queueData: any = { videos: [] };
    let queueSha = "";

    if (queueRes.ok) {
      const queueFile = await queueRes.json();
      queueSha = queueFile.sha;
      const content = Buffer.from(queueFile.content, "base64").toString("utf-8");
      queueData = JSON.parse(content);
    }

    // Add new entry if not exists
    const exists = queueData.videos?.some((v: any) => v.filename === filename);
    if (!exists) {
      queueData.videos = queueData.videos || [];
      queueData.videos.push({
        filename,
        status: "pending_approval",
        uploaded_at: new Date().toISOString(),
        processed_at: null,
      });
    }

    const queueJson = JSON.stringify(queueData, null, 2);
    const queueBase64 = Buffer.from(queueJson).toString("base64");

    const updateQueueRes = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPO}/contents/queue.json`,
      {
        method: "PUT",
        headers: apiHeaders,
        body: JSON.stringify({
          message: `queue: add ${filename}`,
          content: queueBase64,
          branch: BRANCH,
          sha: queueSha || undefined,
        }),
      }
    );

    if (!updateQueueRes.ok) {
      const err = await updateQueueRes.text();
      return NextResponse.json(
        { message: `Queue update failed: ${err}` },
        { status: updateQueueRes.status }
      );
    }

    return NextResponse.json({
      message: `Uploaded ${filename} successfully`,
      filename,
    });
  } catch (e: any) {
    return NextResponse.json(
      { message: `Server error: ${e.message}` },
      { status: 500 }
    );
  }
}
