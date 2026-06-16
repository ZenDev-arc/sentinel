/**
 * Sample TypeScript application with intentional bugs for SENTINEL testing.
 * DO NOT use this code in production.
 */

import * as crypto from "crypto";
import * as fs from "fs";
import * as path from "path";
import * as child_process from "child_process";
import axios from "axios";

// ── Database helpers ──────────────────────────────────────────────────────────

// BUG 1: SQL injection — user input concatenated directly into query string
async function getUser(db: any, username: string) {
  const query = "SELECT * FROM users WHERE username = '" + username + "'";
  return await db.query(query);
}

// BUG 2: N+1 query — fetches comments for each post in a loop
async function getUserPostsWithComments(db: any, userId: number) {
  const posts = await db.query("SELECT id, title FROM posts WHERE user_id = $1", [userId]);
  const result = [];
  for (const post of posts.rows) {
    // Executes one query per post instead of a JOIN
    const comments = await db.query("SELECT * FROM comments WHERE post_id = $1", [post.id]);
    result.push({ post, comments: comments.rows });
  }
  return result;
}

// BUG 3: No error handling — database errors silently swallowed, no rollback
async function deleteUser(db: any, userId: number) {
  await db.query("DELETE FROM sessions WHERE user_id = $1", [userId]);
  await db.query("DELETE FROM posts WHERE user_id = $1", [userId]);
  await db.query("DELETE FROM users WHERE id = $1", [userId]);
}

// ── Auth helpers ──────────────────────────────────────────────────────────────

// BUG 4: Weak hashing — MD5 with no salt, cryptographically broken
function hashPassword(password: string): string {
  return crypto.createHash("md5").update(password).digest("hex");
}

function checkPassword(password: string, storedHash: string): boolean {
  return hashPassword(password) === storedHash;
}

// BUG 5: Predictable token — derived from email + hardcoded secret, not random
function generateResetToken(email: string): string {
  const secret = "hardcoded-secret-123";
  return crypto.createHash("md5").update(email + secret).digest("hex");
}

// BUG 6: Hardcoded credentials in source code
const DB_CONFIG = {
  host: "prod-db.internal",
  user: "admin",
  password: "super_secret_prod_password_123",   // hardcoded secret
  database: "myapp_prod",
};

// ── Business logic ────────────────────────────────────────────────────────────

// BUG 7: Logic error — discount applied twice when > 50%
function calculateDiscount(price: number, discountPercent: number): number {
  if (discountPercent > 50) {
    price = price * (1 - discountPercent / 100);
  }
  const final = price * (1 - discountPercent / 100);
  return final;
}

// BUG 8: No input validation — negative amounts and unknown currencies accepted
function processPayment(amount: number, currency: string = "USD"): object {
  const rates: Record<string, number> = { USD: 1.0, EUR: 1.1, GBP: 1.3 };
  const rate = rates[currency] ?? 1.0;
  return { status: "charged", amount: amount * rate, currency };
}

// ── File system ───────────────────────────────────────────────────────────────

// BUG 9: Path traversal — user-supplied path not sanitised, allows ../../etc/passwd
function loadConfig(configPath: string): object {
  const content = fs.readFileSync(configPath, "utf-8");
  return JSON.parse(content);
}

// BUG 10: Command injection — userId passed directly into shell command
function exportUserData(userId: string, outputDir: string): void {
  const cmd = `pg_dump --table=users --where="id=${userId}" mydb > ${outputDir}/export.sql`;
  child_process.execSync(cmd);  // shell injection if userId contains ; or $()
}

// ── API calls ─────────────────────────────────────────────────────────────────

// BUG 11: SSRF — fetches any URL supplied by caller with no allowlist
async function fetchExternalProfile(url: string): Promise<object> {
  const resp = await axios.get(url, { timeout: 5000 });
  return resp.data;
}

// BUG 12: Insecure direct object reference — no ownership check
async function getDocument(db: any, docId: number, _requestingUserId: number) {
  // Missing: WHERE user_id = $2  (any logged-in user can read any document)
  return await db.query("SELECT * FROM documents WHERE id = $1", [docId]);
}

// BUG 13: Prototype pollution — merging untrusted user data onto object
function mergeUserPreferences(defaults: object, userInput: any): object {
  return Object.assign({}, defaults, userInput);  // userInput can contain __proto__
}

// BUG 14: ReDoS — catastrophic backtracking regex on untrusted input
function validateEmail(email: string): boolean {
  const re = /^([a-zA-Z0-9]+)*@([a-zA-Z0-9]+\.)+[a-zA-Z]{2,}$/;
  return re.test(email);  // catastrophic on crafted input like "a@" + "a".repeat(50)
}

// ── Express route (insecure) ──────────────────────────────────────────────────

// BUG 15: XSS — user input reflected directly into HTML response without escaping
function renderGreeting(req: any, res: any): void {
  const name = req.query.name;
  res.send(`<h1>Hello, ${name}!</h1>`);  // XSS if name = "<script>alert(1)</script>"
}
