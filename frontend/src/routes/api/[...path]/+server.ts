import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

// Backend-for-frontend proxy: the browser only ever talks to this same-origin /api/*
// path. TONEMILL_API_BASE_URL (e.g. http://api:8000 inside Docker) is a server-only env
// var -- an internal Docker-network hostname the browser itself could never resolve.
const API_BASE = env.TONEMILL_API_BASE_URL ?? 'http://localhost:8000';

const HOP_BY_HOP_HEADERS = new Set(['host', 'connection', 'content-length']);

const forward: RequestHandler = async ({ request, params, url }) => {
	const target = `${API_BASE}/${params.path ?? ''}${url.search}`;

	const headers = new Headers();
	for (const [key, value] of request.headers) {
		if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) headers.set(key, value);
	}

	const hasBody = !['GET', 'HEAD'].includes(request.method);
	const response = await fetch(target, {
		method: request.method,
		headers,
		body: hasBody ? await request.arrayBuffer() : undefined
	});

	const responseHeaders = new Headers(response.headers);
	responseHeaders.delete('content-encoding');
	responseHeaders.delete('content-length');
	return new Response(response.status === 204 ? null : await response.arrayBuffer(), {
		status: response.status,
		headers: responseHeaders
	});
};

export const GET = forward;
export const POST = forward;
export const DELETE = forward;
