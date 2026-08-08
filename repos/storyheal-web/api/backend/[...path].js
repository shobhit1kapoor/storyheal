const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

export default async function handler(request, response) {
  const backendOrigin = process.env.BACKEND_ORIGIN?.replace(/\/$/, "");
  if (!backendOrigin?.startsWith("https://")) {
    return response.status(503).json({ detail: "Backend origin is not configured" });
  }

  const pathParts = Array.isArray(request.query.path)
    ? request.query.path
    : [request.query.path || ""];
  const target = new URL(`/${pathParts.map(encodeURIComponent).join("/")}`, backendOrigin);
  for (const [key, value] of Object.entries(request.query)) {
    if (key === "path" || value == null) continue;
    for (const item of Array.isArray(value) ? value : [value]) {
      target.searchParams.append(key, String(item));
    }
  }

  const headers = new Headers();
  for (const [key, value] of Object.entries(request.headers)) {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase()) && value != null) {
      headers.set(key, Array.isArray(value) ? value.join(",") : String(value));
    }
  }

  const method = request.method || "GET";
  const upstream = await fetch(target, {
    method,
    headers,
    body: method === "GET" || method === "HEAD"
      ? undefined
      : typeof request.body === "string"
        ? request.body
        : JSON.stringify(request.body ?? {}),
    redirect: "manual",
  });

  for (const [key, value] of upstream.headers.entries()) {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase()) && key.toLowerCase() !== "content-encoding") {
      response.setHeader(key, value);
    }
  }
  return response.status(upstream.status).send(Buffer.from(await upstream.arrayBuffer()));
}
