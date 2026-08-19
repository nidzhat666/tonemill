<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type ProfileInfo } from '$lib/api-client';
	import { startUpload, uploadFile } from '$lib/upload';
	import { jobsStore } from '$lib/stores/jobs.svelte';
	import { pollJob } from '$lib/polling';
	import JobCard from '$lib/components/JobCard.svelte';

	let profiles = $state<ProfileInfo[]>([]);
	let selectedProfile = $state('auto');
	// GPU-only near-lossless override (FR-027-FR-029); a non-GPU resolved profile fails
	// the job clearly rather than silently ignoring this.
	let maxQuality = $state(false);

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

<h1>Tonemill</h1>
<p>Upload HDR footage, pick a grading profile, get back a correctly tone-mapped result.</p>

<label for="profile-select">Grading profile</label>
<select id="profile-select" bind:value={selectedProfile}>
	<option value="auto">auto</option>
	{#each profiles.filter((p) => p.implemented) as profile (profile.name)}
		<option value={profile.name}>{profile.name}</option>
	{/each}
</select>

<label>
	<input type="checkbox" bind:checked={maxQuality} />
	Maximum quality (GPU only — larger file, longer processing, no visible quality loss)
</label>

<input
	type="file"
	multiple
	accept="video/*"
	onchange={(e) => handleFiles((e.target as HTMLInputElement).files)}
/>

<section class="jobs">
	{#each jobsStore.items as job (job.id)}
		<JobCard {job} />
	{/each}
</section>

<style>
	.jobs {
		margin-top: 1.5rem;
	}
</style>
