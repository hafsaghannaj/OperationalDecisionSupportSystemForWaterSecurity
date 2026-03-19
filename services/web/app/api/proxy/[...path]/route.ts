import { NextRequest, NextResponse } from "next/server";

import { resolveServerApiBaseUrl } from "../../../../lib/api-base";


const REQUEST_HEADERS_TO_FORWARD = ["authorization", "content-type", "x-api-key", "accept"];
const RESPONSE_HEADERS_TO_FORWARD = ["content-type", "cache-control", "etag", "last-modified"];


function buildUpstreamUrl(request: NextRequest, pathSegments: string[]): URL {
  const baseUrl = resolveServerApiBaseUrl();
  const target = new URL(`${baseUrl}/${pathSegments.join("/")}`);
  target.search = request.nextUrl.search;
  return target;
}


function forwardedRequestHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  for (const key of REQUEST_HEADERS_TO_FORWARD) {
    const value = request.headers.get(key);
    if (value) {
      headers.set(key, value);
    }
  }
  return headers;
}


function forwardedResponseHeaders(response: Response): Headers {
  const headers = new Headers();
  for (const key of RESPONSE_HEADERS_TO_FORWARD) {
    const value = response.headers.get(key);
    if (value) {
      headers.set(key, value);
    }
  }
  headers.set("X-ODSSWS-Proxy", "1");
  return headers;
}


async function proxyRequest(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  const { path } = await params;
  const targetUrl = buildUpstreamUrl(request, path);

  try {
    const upstreamResponse = await fetch(targetUrl, {
      method: request.method,
      headers: forwardedRequestHeaders(request),
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      redirect: "follow",
    });

    return new NextResponse(upstreamResponse.body, {
      status: upstreamResponse.status,
      headers: forwardedResponseHeaders(upstreamResponse),
    });
  } catch (error) {
    return NextResponse.json(
      {
        detail:
          error instanceof Error
            ? `API proxy failed: ${error.message}`
            : "API proxy failed for an unknown reason.",
      },
      { status: 502 }
    );
  }
}


export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxyRequest(request, context);
}


export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxyRequest(request, context);
}


export async function PATCH(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxyRequest(request, context);
}


export async function PUT(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxyRequest(request, context);
}


export async function DELETE(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxyRequest(request, context);
}
