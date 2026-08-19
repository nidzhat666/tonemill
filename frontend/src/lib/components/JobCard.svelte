<script lang="ts">
	import type { FileJob } from '$lib/stores/jobs.svelte';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Badge } from '$lib/components/ui/badge/index.js';
	import { Progress } from '$lib/components/ui/progress/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import UploadIcon from '@lucide/svelte/icons/upload';
	import ClockIcon from '@lucide/svelte/icons/clock';
	import LoaderCircleIcon from '@lucide/svelte/icons/loader-circle';
	import CircleCheckBigIcon from '@lucide/svelte/icons/circle-check-big';
	import CircleXIcon from '@lucide/svelte/icons/circle-x';
	import DownloadIcon from '@lucide/svelte/icons/download';

	let { job }: { job: FileJob } = $props();

	type VisualState = 'uploading' | 'queued' | 'running' | 'done' | 'failed';

	const stageLabel: Record<string, string> = {
		downloading: 'Downloading source',
		processing: 'Grading',
		uploading_result: 'Uploading result'
	};

	const statusStyles: Record<
		VisualState,
		{ badgeLabel: string; badge: string; bar: string; icon: typeof UploadIcon }
	> = {
		uploading: {
			badgeLabel: 'Uploading',
			badge: 'border-amber-500/30 bg-amber-500/10 text-amber-400',
			bar: 'bg-amber-500',
			icon: UploadIcon
		},
		queued: {
			badgeLabel: 'Queued',
			badge: 'border-slate-500/30 bg-slate-500/10 text-slate-300',
			bar: 'bg-slate-500',
			icon: ClockIcon
		},
		running: {
			badgeLabel: 'Running',
			badge: 'border-sky-500/30 bg-sky-500/10 text-sky-400',
			bar: 'bg-sky-500',
			icon: LoaderCircleIcon
		},
		done: {
			badgeLabel: 'Done',
			badge: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
			bar: 'bg-emerald-500',
			icon: CircleCheckBigIcon
		},
		failed: {
			badgeLabel: 'Failed',
			badge: 'border-red-500/30 bg-red-500/10 text-red-400',
			bar: 'bg-red-500',
			icon: CircleXIcon
		}
	};

	function visualState(j: FileJob): VisualState {
		if (j.phase === 'uploading') return 'uploading';
		if (j.phase === 'failed' || j.status === 'failed') return 'failed';
		if (j.status === 'done') return 'done';
		if (j.status === 'running') return 'running';
		return 'queued';
	}

	/** Never shows 100% while still running -- only `done` does (FR-005). */
	function cappedRunningPercent(progressPct: number | undefined): number {
		return Math.min(99, Math.floor(progressPct ?? 0));
	}

	let state = $derived(visualState(job));
	let style = $derived(statusStyles[state]);
	let StatusIcon = $derived(style.icon);
	let stageText = $derived(stageLabel[job.stage ?? ''] ?? 'Processing');
</script>

<Card.Root data-status={job.status ?? job.phase}>
	<Card.Content class="flex flex-col gap-1">
		<div class="flex items-center justify-between gap-2">
			<p class="text-foreground min-w-0 flex-1 truncate text-sm font-medium">{job.filename}</p>
			<Badge class="shrink-0 {style.badge}">
				<StatusIcon class="size-3 {state === 'running' ? 'animate-spin' : ''}" />
				{state === 'running' ? stageText : style.badgeLabel}
			</Badge>
		</div>

		{#if job.resolvedProfile}
			<p class="text-muted-foreground text-xs">Profile: {job.resolvedProfile}</p>
		{/if}

		{#if state === 'uploading' || state === 'running'}
			{@const pct =
				state === 'uploading'
					? Math.floor(job.uploadPercent)
					: cappedRunningPercent(job.progressPct)}
			<Progress value={pct} class="mt-1" indicatorClass={style.bar} />
			<p class="text-muted-foreground text-xs">{pct}%</p>
		{/if}

		{#if state === 'failed'}
			<p class="mt-1 text-xs break-words text-red-400">{job.error ?? 'unknown error'}</p>
		{/if}

		{#if state === 'done' && job.resultUrl}
			<Button href={job.resultUrl} download class="mt-2 w-fit">
				<DownloadIcon />
				Download result
			</Button>
		{/if}
	</Card.Content>
</Card.Root>
