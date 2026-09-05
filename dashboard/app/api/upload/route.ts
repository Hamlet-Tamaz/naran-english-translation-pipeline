import { NextRequest, NextResponse } from "next/server";
import { S3Client, PutObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

const R2 = new S3Client({
  region: "auto",
  endpoint: `https://${process.env.R2_ACCOUNT_ID}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId: process.env.R2_ACCESS_KEY_ID!,
    secretAccessKey: process.env.R2_SECRET_ACCESS_KEY!,
  },
});

const BUCKET = process.env.R2_BUCKET_NAME || "naran-videos";

export async function POST(req: NextRequest) {
  try {
    const { filename, contentType } = await req.json();
    if (!filename) {
      return NextResponse.json({ message: "No filename" }, { status: 400 });
    }

    const objectKey = `uploads/${Date.now()}-${filename}`;
    const command = new PutObjectCommand({
      Bucket: BUCKET,
      Key: objectKey,
      ContentType: contentType || "video/mp4",
    });

    const presignedUrl = await getSignedUrl(R2, command, { expiresIn: 600 });
    const publicUrl = `${process.env.R2_PUBLIC_URL}/${objectKey}`;

    return NextResponse.json({
      presignedUrl,
      objectKey,
      publicUrl,
    });
  } catch (e: any) {
    return NextResponse.json({ message: e.message }, { status: 500 });
  }
}
