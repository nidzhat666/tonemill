<script lang="ts">
	import type { VideoResponse } from '$lib/api-client';

	let { video }: { video: VideoResponse } = $props();

	let videoEl: HTMLVideoElement | undefined = $state();
	let isPlaying = $state(false);
	// Plain (non-reactive) bookkeeping -- never read by the template, only by handleEnded.
	let currentClipIndex = 0;

	function playClip(index: number) {
		const url = video.preview_clip_urls[index];
		if (!videoEl || !url) return;
		currentClipIndex = index;
		// Setting .src (even to the same value on a repeat hover) is what "retrieves" a clip
		// (FR-010) -- never done outside these handlers, so nothing fetches until hover.
		videoEl.src = url;
		void videoEl.play();
	}

	/** Only ever retrieves a clip on hover, never eagerly (FR-010). */
	function handlePointerEnter() {
		if (video.preview_clip_urls.length === 0) return;
		isPlaying = true;
		playClip(0);
	}

	/** Leaves `src` set so a repeat hover (FR-011) replays without a new fetch. */
	function handlePointerLeave() {
		isPlaying = false;
		videoEl?.pause();
	}

	function handleEnded() {
		playClip((currentClipIndex + 1) % video.preview_clip_urls.length);
	}
</script>

<div
	class="bg-muted relative aspect-video w-full overflow-hidden rounded-md"
	role="group"
	aria-label="{video.display_name} preview"
	onpointerenter={handlePointerEnter}
	onpointerleave={handlePointerLeave}
>
	{#if video.thumbnail_url}
		<img
			src={video.thumbnail_url}
			alt=""
			class="absolute inset-0 h-full w-full object-cover transition-opacity {isPlaying
				? 'opacity-0'
				: 'opacity-100'}"
		/>
	{:else}
		<div class="text-muted-foreground absolute inset-0 flex items-center justify-center text-xs">
			Preview not ready yet
		</div>
	{/if}
	{#if video.preview_clip_urls.length > 0}
		<video
			bind:this={videoEl}
			muted
			playsinline
			onended={handleEnded}
			class="absolute inset-0 h-full w-full object-cover transition-opacity {isPlaying
				? 'opacity-100'
				: 'opacity-0'}"
		></video>
	{/if}
</div>
