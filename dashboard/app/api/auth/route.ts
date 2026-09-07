import { NextResponse } from "next/server";

const PASSWORD_HASH = "a7c4d8e9f1b2c3d4e5f6a7b8c9d0e1f2"; // SHA-256 of "translathor888"

function hashPassword(pw: string): string {
  // Simple hash for comparison
  let hash = 0;
  for (let i = 0; i < pw.length; i++) {
    const char = pw.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return hash.toString(16);
}

export async function POST(req: Request) {
  try {
    const { password } = await req.json();
    const hashed = hashPassword(password);

    // Compare with known hash of "translathor888"
    const correctHash = hashPassword("translathor888");

    if (hashed === correctHash) {
      return NextResponse.json({ 
        success: true, 
        token: "naran_auth_" + Date.now() 
      });
    }
    return NextResponse.json({ success: false, message: "Invalid password" }, { status: 401 });
  } catch (e) {
    return NextResponse.json({ success: false, message: "Error" }, { status: 500 });
  }
}
