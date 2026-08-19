import type { Handle } from '@sveltejs/kit';

// Backend-for-frontend layer: currently a pass-through. Server-side request
// handling (e.g. proxying/aggregating calls to the Tonemill API) lands here
// as it's needed, per the clarified BFF architecture decision.
export const handle: Handle = async ({ event, resolve }) => resolve(event);
