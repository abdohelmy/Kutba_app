const UPSTREAM = "https://35.207.58.39.sslip.io/api/v1/";
const COOKIE = "khutba_session";
const routes =
  /^(reader\/(mosques(?:\/[\w-]+\/sermons)?|sermons\/[\w-]+(?:\/pdf)?)|auth\/(login|me|register-mosque|logout|forgot-password|reset-password)|owner\/(dashboard|mosques(?:\/[\w-]+)?|users\/[\w-]+(?:\/reset-link)?|sermons|audit|glossary(?:\/(global|mosque)\/[\w-]+)?)|admin\/(profile|password|glossary(?:\/[\w-]+)?|sermons(?:\/[\w-]+(?:\/(title|danish|hide|show|source-text|translate|preview|publish|glossary-candidates|glossary-contributions|segments\/[\w-]+(?:\/alignment)?))?)?))$/;
const liveRoutes=/^(reader\/sermons\/[\w-]+\/live|admin\/sermons\/[\w-]+\/live(?:\/(prepare|audio))?|owner\/live-worker-token)$/;
export const dynamic = "force-dynamic";
async function handle(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const path = (await context.params).path.join("/");
  const origin = new URL(request.url).origin;
  const headers = new Headers({ "Cache-Control": "no-store" });
  const cookie = (value: string, age: number) =>
    `${COOKIE}=${value}; Path=/api; HttpOnly; SameSite=Strict; Max-Age=${age}${origin.startsWith("https:") ? "; Secure" : ""}`;
  if (!routes.test(path)&&!liveRoutes.test(path))
    return Response.json({ detail: "Not found" }, { status: 404, headers });
  if (request.method !== "GET" && request.headers.get("origin") !== origin)
    return Response.json(
      { detail: "Request origin not allowed" },
      { status: 403, headers },
    );
  if (path === "auth/logout") {
    if (request.method !== "POST")
      return Response.json(
        { detail: "Method not allowed" },
        { status: 405, headers },
      );
    headers.set("Set-Cookie", cookie("", 0));
    return Response.json({ status: "ok" }, { headers });
  }
  const token = request.headers
    .get("cookie")
    ?.split(";")
    .map((v) => v.trim())
    .find((v) => v.startsWith(COOKIE + "="))
    ?.slice(COOKIE.length + 1);
  if ((path.startsWith("admin/") || path.startsWith("owner/") || path === "auth/me") && !token)
    return Response.json(
      { detail: "Please sign in to your mosque." },
      { status: 401, headers },
    );
  const upstreamHeaders = new Headers();
  if (token) upstreamHeaders.set("Authorization", `Bearer ${token}`);
  const type = request.headers.get("content-type");
  if (type) upstreamHeaders.set("Content-Type", type);
  const length = Number(request.headers.get("content-length") || 0);
  if (length > 17 * 1024 * 1024)
    return Response.json(
      { detail: "Choose a file smaller than 15 MB." },
      { status: 413, headers },
    );
  try {
    const body =
      request.method === "GET" ? undefined : await request.arrayBuffer();
    if (body && body.byteLength > 17 * 1024 * 1024)
      return Response.json(
        { detail: "Upload too large" },
        { status: 413, headers },
      );
    const query = new URL(request.url).search;
    const response = await fetch(UPSTREAM + path + query, {
      method: request.method,
      headers: upstreamHeaders,
      body,
      redirect: "manual",
      signal: AbortSignal.timeout(path === "admin/sermons" ? 120000 : 45000),
    });
    if(response.status>=300&&response.status<400)throw Error("Unexpected API redirect");
    if (path === "auth/login" && response.ok) {
      const data = (await response.json()) as { access_token: string };
      if (!data.access_token || /[\s;]/.test(data.access_token))
        throw Error("Invalid token");
      headers.set("Set-Cookie", cookie(data.access_token, 8 * 60 * 60));
      return Response.json({ status: "ok" }, { headers });
    }
    if (response.status === 401) headers.set("Set-Cookie", cookie("", 0));
    for (const key of ["content-type", "content-disposition"]) {
      const value = response.headers.get(key);
      if (value) headers.set(key, value);
    }
    headers.set("X-Content-Type-Options", "nosniff");
    return new Response(response.body, { status: response.status, headers });
  } catch (error) {
    console.error("Khutba upstream unavailable", error instanceof Error ? error.message : "Network error");
    return Response.json(
      {
        detail:
          "The server is unavailable. Its usual hours are Friday, 10:00–15:00 Copenhagen time. If it should be online, please try again shortly.",
      },
      { status: 503, headers },
    );
  }
}
export {
  handle as GET,
  handle as POST,
  handle as PUT,
  handle as PATCH,
  handle as DELETE,
};
