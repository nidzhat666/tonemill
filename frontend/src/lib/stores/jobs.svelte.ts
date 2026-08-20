import type { JobStage, JobStatus, JobStatusResponse } from '$lib/api-client';

// One entry per submitted file (FR-026): each is tracked and rendered independently, so
// one file failing never affects the others (SC-009).
export type FileJobPhase = 'uploading' | 'submitted' | 'failed';

export interface FileJob {
	id: string;
	filename: string;
	phase: FileJobPhase;
	uploadPercent: number;
	jobId?: string;
	status?: JobStatus;
	stage?: JobStage;
	progressPct?: number;
	resolvedProfile?: string | null;
	resultUrl?: string | null;
	error?: string | null;
}

let nextLocalId = 0;

/**
 * A locally-unique tracking key, not crypto.randomUUID(): that API requires a secure
 * context (HTTPS or localhost) and throws on plain-HTTP LAN access -- this deployment's
 * actual access pattern (no reverse proxy/TLS in scope for v1).
 */
function nextId(): string {
	nextLocalId += 1;
	return `${Date.now()}-${nextLocalId}`;
}

/** source_key is "sources/{uuid}/{original filename}" (see uploads.py's _safe_key). */
function filenameFromSourceKey(sourceKey: string): string {
	return sourceKey.split('/').pop() ?? sourceKey;
}

function fromServerJob(job: JobStatusResponse): FileJob {
	return {
		id: nextId(),
		filename: filenameFromSourceKey(job.source_key),
		phase: 'submitted',
		uploadPercent: 100,
		jobId: job.job_id,
		status: job.status,
		stage: job.stage,
		progressPct: job.progress_pct,
		resolvedProfile: job.resolved_profile,
		resultUrl: job.result_url,
		error: job.error
	};
}

/** A job the dashboard can dismiss: has a server-side job record, and isn't in progress
 * (FR-002-FR-004) -- a still-uploading or not-yet-submitted local entry has no jobId yet and
 * is never dismissable.
 */
export function isDismissable(job: FileJob): boolean {
	return Boolean(job.jobId) && (job.status === 'done' || job.status === 'failed');
}

class JobsStore {
	items = $state<FileJob[]>([]);

	add(filename: string): FileJob {
		const job: FileJob = {
			id: nextId(),
			filename,
			phase: 'uploading',
			uploadPercent: 0
		};
		this.items.push(job);
		return job;
	}

	update(id: string, patch: Partial<FileJob>): void {
		const job = this.items.find((j) => j.id === id);
		if (job) Object.assign(job, patch);
	}

	/** Drops one job from the dashboard view only -- never touches its video (FR-005). */
	remove(id: string): void {
		this.items = this.items.filter((j) => j.id !== id);
	}

	/** Drops every dismissable job (FR-003) -- server-side dismissal already happened by the
	 * time this is called; this just reflects that locally without a full re-fetch.
	 */
	clearDismissable(): void {
		this.items = this.items.filter((j) => !isDismissable(j));
	}

	/**
	 * Merges in every job Redis currently knows about, not just ones submitted from this
	 * browser session -- a job already tracked locally (matched by jobId) is updated in
	 * place rather than duplicated.
	 */
	hydrateFromServer(serverJobs: JobStatusResponse[]): void {
		for (const serverJob of serverJobs) {
			const existing = this.items.find((j) => j.jobId === serverJob.job_id);
			if (existing) {
				Object.assign(existing, {
					status: serverJob.status,
					stage: serverJob.stage,
					progressPct: serverJob.progress_pct,
					resolvedProfile: serverJob.resolved_profile,
					resultUrl: serverJob.result_url,
					error: serverJob.error
				});
			} else {
				this.items.push(fromServerJob(serverJob));
			}
		}
	}
}

export const jobsStore = new JobsStore();
