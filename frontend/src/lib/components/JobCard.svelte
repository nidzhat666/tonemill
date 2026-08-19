<script lang="ts">
	import type { FileJob } from '$lib/stores/jobs.svelte';

	let { job }: { job: FileJob } = $props();

	const stageLabel: Record<string, string> = {
		downloading: 'Downloading source',
		processing: 'Grading',
		uploading_result: 'Uploading result'
	};

	function label(j: FileJob): string {
		if (j.phase === 'uploading') return `Uploading… ${j.uploadPercent.toFixed(0)}%`;
		if (j.phase === 'failed' || j.status === 'failed')
			return `Failed: ${j.error ?? 'unknown error'}`;
		if (j.status === 'queued') return 'Queued';
		if (j.status === 'running') {
			// Progress caps below 100 until the job actually reaches `done` (FR-005) --
			// Math.floor, not toFixed/round, so a still-running job never displays "100%".
			const pct = Math.min(99, Math.floor(j.progressPct ?? 0));
			return `${stageLabel[j.stage ?? ''] ?? 'Processing'} — ${pct}%`;
		}
		if (j.status === 'done') return 'Done';
		return 'Waiting…';
	}
</script>

<div class="job-card" data-status={job.status ?? job.phase}>
	<p class="filename">{job.filename}</p>
	<p class="status">{label(job)}</p>
	{#if job.resolvedProfile}
		<p class="profile">Profile: {job.resolvedProfile}</p>
	{/if}
	{#if job.status === 'done' && job.resultUrl}
		<a class="download" href={job.resultUrl} download>Download result</a>
	{/if}
</div>

<style>
	.job-card {
		border: 1px solid #444;
		border-radius: 0.5rem;
		padding: 0.75rem 1rem;
		margin-block: 0.5rem;
	}
	.filename {
		font-weight: 600;
	}
	.status {
		opacity: 0.8;
	}
	.job-card[data-status='failed'] .status {
		color: #d33;
	}
	.download {
		display: inline-block;
		margin-top: 0.5rem;
	}
</style>
