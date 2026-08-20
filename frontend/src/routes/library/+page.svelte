<script lang="ts">
	import { onMount } from 'svelte';
	import { libraryStore } from '$lib/stores/library.svelte';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import FolderCard from '$lib/components/FolderCard.svelte';
	import VideoCard from '$lib/components/VideoCard.svelte';
	import FolderPlusIcon from '@lucide/svelte/icons/folder-plus';

	const DRAG_MIME = 'application/x-tonemill-video-ids';

	let newFolderName = $state('');
	let createError = $state<string | null>(null);
	let isUnsortedDragOver = $state(false);

	onMount(() => {
		void libraryStore.load();
	});

	async function handleCreateFolder() {
		const name = newFolderName.trim();
		if (!name) return;
		createError = null;
		try {
			await libraryStore.createFolder(name);
			newFolderName = '';
		} catch (error) {
			createError = error instanceof Error ? error.message : String(error);
		}
	}

	/** Dragging a video that's part of the current selection drags the whole selection;
	 * dragging an unselected one drags just that video (FR-010, FR-011).
	 */
	function handleDragStart(videoId: string, event: DragEvent) {
		const ids = libraryStore.isSelected(videoId) ? [...libraryStore.selectedVideoIds] : [videoId];
		event.dataTransfer?.setData(DRAG_MIME, JSON.stringify(ids));
		if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
	}

	function idsFromDrop(event: DragEvent): string[] {
		const raw = event.dataTransfer?.getData(DRAG_MIME);
		if (!raw) return [];
		try {
			return JSON.parse(raw) as string[];
		} catch {
			return [];
		}
	}

	function handleDropOnFolder(folderId: string, event: DragEvent) {
		const ids = idsFromDrop(event);
		if (ids.length > 0) void libraryStore.moveVideos(folderId, ids);
	}

	function handleDropOnUnsorted(event: DragEvent) {
		event.preventDefault();
		isUnsortedDragOver = false;
		const ids = idsFromDrop(event);
		if (ids.length > 0) void libraryStore.moveVideos(null, ids);
	}

	async function handleDeleteFolder(folderId: string) {
		await libraryStore.deleteFolder(folderId);
	}
</script>

<div class="mx-auto max-w-3xl px-4 py-8 sm:px-6 md:px-8">
	<h1 class="text-foreground text-2xl font-semibold">Library</h1>
	<p class="text-muted-foreground mt-1 text-sm">
		Organize your graded videos into folders — drag one video, or a selected batch, onto a folder to
		move it.
	</p>

	<Card.Root class="mt-6">
		<Card.Content class="flex flex-col gap-2">
			<label for="new-folder-name" class="text-foreground text-sm font-medium">New folder</label>
			<div class="flex gap-2">
				<input
					id="new-folder-name"
					bind:value={newFolderName}
					onkeydown={(e) => e.key === 'Enter' && handleCreateFolder()}
					placeholder="e.g. Kavos shoot"
					class="border-input bg-background text-foreground flex-1 rounded-md border px-3 py-1.5 text-sm"
				/>
				<Button onclick={handleCreateFolder}>
					<FolderPlusIcon />
					Create
				</Button>
			</div>
			{#if createError}
				<p class="text-xs text-red-400">{createError}</p>
			{/if}
		</Card.Content>
	</Card.Root>

	{#if libraryStore.selectedVideoIds.size > 0}
		<div class="mt-4 flex items-center justify-between">
			<p class="text-muted-foreground text-sm">
				{libraryStore.selectedVideoIds.size} selected — drag onto a folder to move them together
			</p>
			<Button variant="ghost" size="sm" onclick={() => libraryStore.clearSelection()}>
				Clear selection
			</Button>
		</div>
	{/if}

	{#each libraryStore.folders as folder (folder.folder_id)}
		<section class="mt-6">
			<FolderCard {folder} onDrop={handleDropOnFolder} onDelete={handleDeleteFolder} />
			{#if libraryStore.videosInFolder(folder.folder_id).length > 0}
				<div class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
					{#each libraryStore.videosInFolder(folder.folder_id) as video (video.video_id)}
						<VideoCard
							{video}
							selected={libraryStore.isSelected(video.video_id)}
							onToggleSelect={(id) => libraryStore.toggleSelected(id)}
							onDragStart={handleDragStart}
						/>
					{/each}
				</div>
			{/if}
		</section>
	{/each}

	<div
		class="mt-6 rounded-lg border-2 border-dashed p-3 transition-colors {isUnsortedDragOver
			? 'border-sky-400 bg-sky-500/10'
			: 'border-border'}"
		role="region"
		aria-label="Unsorted videos (drop target)"
		ondragover={(e: DragEvent) => {
			e.preventDefault();
			isUnsortedDragOver = true;
		}}
		ondragleave={() => (isUnsortedDragOver = false)}
		ondrop={handleDropOnUnsorted}
	>
		<h2 class="text-foreground text-sm font-medium">Unsorted</h2>
		{#if libraryStore.unsortedVideos().length === 0}
			<p class="text-muted-foreground mt-2 text-sm">
				No unsorted videos — drag a video here to move it out of a folder.
			</p>
		{:else}
			<div class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
				{#each libraryStore.unsortedVideos() as video (video.video_id)}
					<VideoCard
						{video}
						selected={libraryStore.isSelected(video.video_id)}
						onToggleSelect={(id) => libraryStore.toggleSelected(id)}
						onDragStart={handleDragStart}
					/>
				{/each}
			</div>
		{/if}
	</div>
</div>
