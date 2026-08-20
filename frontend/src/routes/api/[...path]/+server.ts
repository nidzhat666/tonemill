import { env } from '$env/dynamic/private';
import { Agent } from 'undici';
import type { RequestHandler } from './$types';

// Backend-for-frontend proxy: the browser only ever talks to this same-origin /api/*
// path. TONEMILL_API_BASE_URL (e.g. http://api:8000 inside Docker) is a server-only env
// var -- an internal Docker-network hostname the browser itself could never resolve.
const API_BASE = env.TONEMILL_API_BASE_URL ?? 'http://localhost:8000';

const HOP_BY_HOP_HEADERS = new Set(['host', 'connection', 'content-length']);

/** Node's fetch (undici) accepts `dispatcher`, but lib.dom.d.ts's RequestInit doesn't know it. */
type NodeRequestInit = RequestInit & { dispatcher?: Agent };

/**
 * A fresh, single-use connection per proxied request, never pooled. Reusing Node's shared
 * keep-alive pool to the API here intermittently returned a stale response (a real, older
 * `{"detail":"Not Found"}` body from an unrelated earlier request, not a fresh error) for a
 * route that genuinely exists -- reproduced live, and tuning either side's keep-alive
 * timeout didn't fully eliminate it (see docker/api.Dockerfile's history). A dedicated
 * connection that's closed after each request removes the reuse entirely.
 */
function freshDispatcher(): Agent {
	return new Agent({ connections: 1, pipelining: 0 });
}

const forward: RequestHandler = async ({ request, params, url }) => {
	const target = `${API_BASE}/${params.path ?? ''}${url.search}`;

	const headers = new Headers();
	for (const [key, value] of request.headers) {
		if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) headers.set(key, value);
	}

	const hasBody = !['GET', 'HEAD'].includes(request.method);
	const dispatcher = freshDispatcher();
	try {
		const requestInit: NodeRequestInit = {
			method: request.method,
			headers,
			body: hasBody ? await request.arrayBuffer() : undefined,
			dispatcher
		};
		const response = await fetch(target, requestInit);

		const responseHeaders = new Headers(response.headers);
		responseHeaders.delete('content-encoding');
		responseHeaders.delete('content-length');
		return new Response(response.status === 204 ? null : await response.arrayBuffer(), {
			status: response.status,
			headers: responseHeaders
		});
	} finally {
		await dispatcher.close();
	}
};

export const GET = forward;
export const POST = forward;
export const DELETE = forward;
