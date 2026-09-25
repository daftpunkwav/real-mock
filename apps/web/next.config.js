/** @type {import('next').NextConfig} */
// Backend default port: prefer BACKEND_PORT / NEXT_PUBLIC_API_BASE, else 8081.
// Port plan: frontend 8080 / backend 8081; additional services 8082, 8083, …
const backendOrigin = (
  process.env.NEXT_PUBLIC_API_BASE ||
  `http://127.0.0.1:${process.env.BACKEND_PORT || "8081"}`
).replace(/\/+$/, "");

const wsOrigin = (
  process.env.NEXT_PUBLIC_WS_URL ||
  backendOrigin.replace(/^http/, "ws")
).replace(/\/+$/, "");

const streamOrigin = (
  process.env.NEXT_PUBLIC_STREAM_API_BASE || backendOrigin
).replace(/\/+$/, "");

function originHost(url) {
  try {
    return new URL(url).origin;
  } catch {
    return "";
  }
}

// api.ts resolveBackendUrl aligns backend hostname to the page hostname (localhost ↔ 127.0.0.1),
// so CSP must allow both loopback hostnames; otherwise localhost pages fail connect-src.
function connectSrcEntries(url) {
  const origin = originHost(url);
  if (!origin) return [];
  try {
    const u = new URL(origin);
    if (u.hostname === "127.0.0.1") {
      const v = new URL(origin);
      v.hostname = "localhost";
      return [origin, v.origin];
    }
    if (u.hostname === "localhost") {
      const v = new URL(origin);
      v.hostname = "127.0.0.1";
      return [origin, v.origin];
    }
  } catch {
    /* Non-standard URL — keep a single value */
  }
  return [origin];
}

const connectSrc = [
  "'self'",
  ...connectSrcEntries(backendOrigin),
  ...connectSrcEntries(streamOrigin),
  ...connectSrcEntries(wsOrigin),
  // TalkingHead / Three may fetch blob textures
  "blob:",
]
  .filter(Boolean)
  .filter((v, i, a) => a.indexOf(v) === i)
  .join(" ");

// Resume preview page images are server-rendered by the backend (8081); img-src must allow that origin
const imgSrc = [
  "'self'",
  "data:",
  "blob:",
  ...connectSrcEntries(backendOrigin),
]
  .filter(Boolean)
  .filter((v, i, a) => a.indexOf(v) === i)
  .join(" ");

// Log at startup so CSP connect-src lock is easy to confirm
if (process.env.NODE_ENV !== "production") {
  console.info(`[next.config] connect-src locked → ${backendOrigin}`);
}

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(self), microphone=(self), geolocation=()",
  },
  // CSP: tighten connect-src; TalkingHead/Three still need unsafe-eval
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      // unsafe-eval: TalkingHead / Three runtime; unsafe-inline: theme bootstrap script
      "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
      "style-src 'self' 'unsafe-inline'",
      `img-src ${imgSrc}`,
      "font-src 'self' data:",
      `connect-src ${connectSrc}`,
      "media-src 'self' blob: data:",
      "worker-src 'self' blob:",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; "),
  },
];

if (process.env.NODE_ENV === "production") {
  securityHeaders.push({
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  });
}

const nextConfig = {
  // Do not switch `next dev` to --turbopack: talkinghead's runtime-built
  // import(moduleName) fails the Turbopack build with "Can't resolve <dynamic>".
  transpilePackages: ["@met4citizen/talkinghead", "three"],
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
      {
        source: "/avatars/:path*",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=31536000, immutable",
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
