import { NextResponse } from "next/server";

export async function POST(req: Request) {
  try {
    const { filename, version } = await req.json();
    const token = process.env.GITHUB_TOKEN;
    if (!token) {
      return NextResponse.json({ message: "GITHUB_TOKEN not configured" }, { status: 500 });
    }

    const repo = "Hamlet-Tamaz/naran-english-translation-pipeline";
    const videoId = filename.replace(".mp4", "");
    const folderPath = `processed/${videoId}/v${version}`;

    // GitHub doesn't have a recursive delete API, so we need to list and delete each file
    const listRes = await fetch(`https://api.github.com/repos/${repo}/git/trees/main?recursive=1`, {
      headers: { Authorization: `token ${token}`, Accept: "application/vnd.github.v3+json" }
    });
    const treeData = await listRes.json();
    const filesToDelete = treeData.tree
      .filter((item: any) => item.path.startsWith(folderPath + "/") && item.type === "blob")
      .map((item: any) => item.path);

    // Delete each file
    for (const filePath of filesToDelete) {
      const getRes = await fetch(`https://api.github.com/repos/${repo}/contents/${filePath}?ref=main`, {
        headers: { Authorization: `token ${token}` }
      });
      if (getRes.ok) {
        const fileData = await getRes.json();
        await fetch(`https://api.github.com/repos/${repo}/contents/${filePath}`, {
          method: "DELETE",
          headers: { Authorization: `token ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify({ message: `delete: remove ${filePath}`, sha: fileData.sha, branch: "main" })
        });
      }
    }

    // Update versions.json
    const versionsPath = `processed/${videoId}/versions.json`;
    const versionsRes = await fetch(`https://api.github.com/repos/${repo}/contents/${versionsPath}?ref=main`, {
      headers: { Authorization: `token ${token}` }
    });
    if (versionsRes.ok) {
      const vData = await versionsRes.json();
      const versions = JSON.parse(Buffer.from(vData.content, "base64").toString());
      versions.versions = versions.versions.filter((v: any) => v.number !== version);
      const updated = JSON.stringify(versions, null, 2);
      await fetch(`https://api.github.com/repos/${repo}/contents/${versionsPath}`, {
        method: "PUT",
        headers: { Authorization: `token ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ message: `update: remove v${version} from versions.json`, content: Buffer.from(updated).toString("base64"), sha: vData.sha, branch: "main" })
      });
    }

    return NextResponse.json({ message: `Version ${version} deleted successfully` });
  } catch (e: any) {
    return NextResponse.json({ message: `Error: ${e.message}` }, { status: 500 });
  }
}
