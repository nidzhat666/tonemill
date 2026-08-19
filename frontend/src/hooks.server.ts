import { env } from '$env/dynamic/private';
import type { Handle } from '@sveltejs/kit';
import { checkBasicAuth } from '$lib/auth';

const UNAUTHORIZED = new Response('Unauthorized', {
	status: 401,
	headers: { 'WWW-Authenticate': 'Basic realm="Tonemill"' }
});

// Backend-for-frontend layer: gates every request behind a single shared username/password
// (FR-011-FR-013) before falling through to SvelteKit's normal resolve/proxying.
export const handle: Handle = async ({ event, resolve }) => {
	const { TONEMILL_AUTH_USERNAME, TONEMILL_AUTH_PASSWORD } = env;
	if (!TONEMILL_AUTH_USERNAME || !TONEMILL_AUTH_PASSWORD) return resolve(event);

	const authorized = checkBasicAuth(
		event.request.headers.get('authorization'),
		TONEMILL_AUTH_USERNAME,
		TONEMILL_AUTH_PASSWORD
	);
	if (!authorized) return UNAUTHORIZED;

	return resolve(event);
};
