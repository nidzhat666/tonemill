import { api, type JobStatusResponse } from './api-client';

const POLL_INTERVAL_MS = 2000;

/**
 * Poll a job's status until it reaches a terminal state (done/failed), calling onUpdate on
 * every response so the UI updates live without a page reload (FR-020 acceptance scenario
 * 2). Returns a stop function in case the caller navigates away early.
 */
export function pollJob(
	jobId: string,
	onUpdate: (status: JobStatusResponse) => void,
	onError: (error: Error) => void
): () => void {
	let stopped = false;

	async function tick() {
		if (stopped) return;
		try {
			const status = await api.getJobStatus(jobId);
			if (stopped) return;
			onUpdate(status);
			if (status.status === 'done' || status.status === 'failed') return;
		} catch (error) {
			onError(error instanceof Error ? error : new Error(String(error)));
			return;
		}
		setTimeout(tick, POLL_INTERVAL_MS);
	}

	tick();
	return () => {
		stopped = true;
	};
}
