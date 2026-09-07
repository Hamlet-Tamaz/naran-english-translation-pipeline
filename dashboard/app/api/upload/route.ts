import { NextRequest, NextResponse } from "next/server";
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

const OWNER = "Hamlet-Tamaz";
const REPO = "naran-english-translation-pipeline";
const BRANCH = "main";

function getR2Client() {
  const accountId = process.env.R2_ACCOUNT_ID;
  const accessKey = process.env.R2_ACCESS_KEY_ID;
  const secretKey = process.env.R2_SECRET_ACCESS_KEY;
  if (!accountId || !accessKey || !secretKey) return null;
  return new S3Client({
    region: "auto",
    endpoint: `https://${accountId}.r2.cloudflarestorage.com`,
    credentials: { accessKeyId: accessKey, secretAccessKey: secretKey },
  });
}

export async function POST(req: NextRequest) {
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return NextResponse.json({ message: "GITHUB_TOKEN not configured" }, { status: 500 });
  }

  try {
    const contentType = req.headers.get("content-type") || "";

    if (contentType.includes("multipart/form-data")) {
      return handleDirectUpload(req, token);
    }

    const { filename, contentType: fileType } = await req.json();
    if (!filename) {
      return NextResponse.json({ message: "No filename" }, { status: 400 });
    }

    const r2 = getR2Client();
    if (!r2) {
      return NextResponse.json({ message: "R2 not configured" }, { status: 503 });
    }

    const bucket = process.env.R2_BUCKET_NAME || "naran-videos";
    const objectKey = `uploads/${Date.now()}-${filename}`;
    const command = new PutObjectCommand({
      Bucket: bucket,
      Key: objectKey,
      ContentType: fileType || "video/mp4",
    });

    const presignedUrl = await getSignedUrl(r2, command, { expiresIn: 600 });
    const publicUrl = `${process.env.R2_PUBLIC_URL}/${objectKey}`;

    return NextResponse.json({ presignedUrl, objectKey, publicUrl, mode: "r2" });
  } catch (e: any) {
    return NextResponse.json({ message: e.message }, { status: 500 });
  }
}

async function handleDirectUpload(req: NextRequest, token: string) {
  const formData = await req.formData();
  const file = formData.get("file") as File;

  if (!file) {
    return NextResponse.json({ message: "No file provided" }, { status: 400 });
  }

  if (!file.type.startsWith("video/")) {
    return NextResponse.json({ message: "Only video files allowed" }, { status: 400 });
  }

  if (file.size > 4.5 * 1024 * 1024) {
    return NextResponse.json(
      { message: "File too large for direct upload (max 4.5MB). Enable R2 for unlimited size." },
      { status: 400 }
    );
  }

  const filename = file.name;
  const path = `incoming/${filename}`;
  const bytes = await file.arrayBuffer();
  const base64 = Buffer.from(bytes).toString("base64");

  const apiHeaders = {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github.v3+json",
    "Content-Type": "application/json",
  };

  const uploadRes = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/contents/${path}`,
    {
      method: "PUT",
      headers: apiHeaders,
      body: JSON.stringify({ message: `upload: ${filename}`, content: base64, branch: BRANCH }),
    }
  );

  if (!uploadRes.ok) {
    const err = await uploadRes.text();
    return NextResponse.json({ message: `GitHub upload failed: ${err}` }, { status: uploadRes.status });
  }

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

  queueData.videos = queueData.videos || [];
  queueData.videos.push({
    filename,
    status: "pending_approval",
    uploaded_at: new Date().toISOString(),
    processed_at: null,
  });

  const updateRes = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/contents/queue.json`,
    {
      method: "PUT",
      headers: apiHeaders,
      body: JSON.stringify({
        message: `queue: add ${filename}`,
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

  return NextResponse.json({ message: "Uploaded", filename, mode: "direct" });
}
