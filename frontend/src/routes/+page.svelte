<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type ProfileInfo } from '$lib/api-client';
	import { startUpload, uploadFile } from '$lib/upload';
	import { jobsStore } from '$lib/stores/jobs.svelte';
	import { pollJob } from '$lib/polling';
	import JobCard from '$lib/components/JobCard.svelte';
	import * as Select from '$lib/components/ui/select/index.js';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Checkbox } from '$lib/components/ui/checkbox/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import ClapperboardIcon from '@lucide/svelte/icons/clapperboard';
	import UploadIcon from '@lucide/svelte/icons/upload';

	let profiles = $state<ProfileInfo[]>([]);
	let selectedProfile = $state('auto');
	// GPU-only near-lossless override (FR-027-FR-029); a non-GPU resolved profile fails
	// the job clearly rather than silently ignoring this.
	let maxQuality = $state(false);
	let fileInput: HTMLInputElement | undefined = $state();

	const profileOptions = $derived([
		{ value: 'auto', label: 'auto' },
		...profiles.filter((p) => p.implemented).map((p) => ({ value: p.name, label: p.name }))
	]);
	const selectedProfileLabel = $derived(
		profileOptions.find((p) => p.value === selectedProfile)?.label ?? 'Select a profile'
	);

	onMount(async () => {
		profiles = await api.listProfiles();
		await loadAllJobs();
	});

	/** Polls jobId and reflects every update onto the local job tracked as localId. */
	function trackJob(localId: string, jobId: string) {
		pollJob(
			jobId,
			(status) => {
				jobsStore.update(localId, {
					status: status.status,
					stage: status.stage,
					progressPct: status.progress_pct,
					resolvedProfile: status.resolved_profile,
					resultUrl: status.result_url,
					error: status.error
				});
			},
			(error) => {
				jobsStore.update(localId, { phase: 'failed', error: error.message });
			}
		);
	}

	// Shows every job in Redis, not just ones submitted from this browser session --
	// still-running jobs keep polling for live progress after hydration.
	async function loadAllJobs() {
		const serverJobs = await api.listJobs();
		jobsStore.hydrateFromServer(serverJobs);
		for (const serverJob of serverJobs) {
			if (serverJob.status === 'done' || serverJob.status === 'failed') continue;
			const job = jobsStore.items.find((j) => j.jobId === serverJob.job_id);
			if (job) trackJob(job.id, serverJob.job_id);
		}
	}

	// Each selected file is uploaded and submitted as its own independent job (FR-026) --
	// one file's failure never blocks or delays the others.
	async function handleFiles(fileList: FileList | null) {
		if (!fileList) return;
		for (const file of Array.from(fileList)) {
			void submitFile(file);
		}
	}

	async function submitFile(file: File) {
		const job = jobsStore.add(file.name);
		try {
			const session = await startUpload(file);
			const s3Key = await uploadFile(file, session, (progress) => {
				jobsStore.update(job.id, { uploadPercent: progress.percent });
			});

			const submitted = await api.submitJob(s3Key, selectedProfile, maxQuality);
			jobsStore.update(job.id, {
				phase: 'submitted',
				jobId: submitted.job_id,
				status: submitted.status
			});

			trackJob(job.id, submitted.job_id);
		} catch (error) {
			jobsStore.update(job.id, {
				phase: 'failed',
				error: error instanceof Error ? error.message : String(error)
			});
		}
	}
</script>

<div class="mx-auto max-w-3xl px-4 py-8 sm:px-6 md:px-8">
	<div class="flex items-center gap-2">
		<ClapperboardIcon class="size-6 text-sky-400" />
		<h1 class="text-foreground text-2xl font-semibold">Tonemill</h1>
	</div>
	<p class="text-muted-foreground mt-1 text-sm">
		Upload HDR footage, pick a grading profile, get back a correctly tone-mapped result.
	</p>

	<Card.Root class="mt-8">
		<Card.Content class="flex flex-col gap-4">
			<div>
				<label for="profile-select" class="text-foreground text-sm font-medium">
					Grading profile
				</label>
				<Select.Root type="single" name="profile" bind:value={selectedProfile}>
					<Select.Trigger id="profile-select" class="mt-1 w-full sm:max-w-xs">
						{selectedProfileLabel}
					</Select.Trigger>
					<Select.Content>
						{#each profileOptions as option (option.value)}
							<Select.Item value={option.value} label={option.label}>{option.label}</Select.Item>
						{/each}
					</Select.Content>
				</Select.Root>
			</div>

			<label class="text-foreground flex items-start gap-2 text-sm">
				<Checkbox bind:checked={maxQuality} class="mt-0.5" />
				<span>
					Maximum quality (GPU only — larger file, longer processing, no visible quality loss)
				</span>
			</label>

			<div>
				<Button variant="outline" onclick={() => fileInput?.click()}>
					<UploadIcon />
					Choose files
				</Button>
				<input
					bind:this={fileInput}
					type="file"
					multiple
					accept="video/*"
					class="hidden"
					onchange={(e) => handleFiles((e.target as HTMLInputElement).files)}
				/>
			</div>
		</Card.Content>
	</Card.Root>

	<section class="mt-6 space-y-3">
		{#if jobsStore.items.length === 0}
			<div
				class="border-border text-muted-foreground rounded-lg border border-dashed px-4 py-10 text-center text-sm"
			>
				No jobs yet — upload a file to get started.
			</div>
		{:else}
			{#each jobsStore.items as job (job.id)}
				<JobCard {job} />
			{/each}
		{/if}
	</section>
</div>
