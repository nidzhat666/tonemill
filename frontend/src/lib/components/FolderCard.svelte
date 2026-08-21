<script lang="ts">
	import type { FolderResponse } from '$lib/api-client';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import FolderIcon from '@lucide/svelte/icons/folder';
	import TrashIcon from '@lucide/svelte/icons/trash-2';
	import ChevronRightIcon from '@lucide/svelte/icons/chevron-right';
	import ChevronDownIcon from '@lucide/svelte/icons/chevron-down';

	let {
		folder,
		videoCount,
		expanded,
		onToggleExpanded,
		onDrop,
		onDelete
	}: {
		folder: FolderResponse;
		// Live count from the library store's current videos, not `folder.video_count` --
		// that field is a snapshot from the last GET /folders and goes stale the moment a
		// video is moved locally (no full re-fetch happens after a move).
		videoCount: number;
		expanded: boolean;
		onToggleExpanded: (folderId: string) => void;
		onDrop: (folderId: string, event: DragEvent) => void;
		onDelete: (folderId: string) => void;
	} = $props();

	let isDragOver = $state(false);
</script>

<Card.Root
	class="transition-colors {isDragOver ? 'border-sky-400 bg-sky-500/10' : ''}"
	ondragover={(e: DragEvent) => {
		e.preventDefault();
		isDragOver = true;
	}}
	ondragleave={() => (isDragOver = false)}
	ondrop={(e: DragEvent) => {
		e.preventDefault();
		isDragOver = false;
		onDrop(folder.folder_id, e);
	}}
>
	<Card.Content class="flex items-center justify-between gap-2">
		<button
			type="button"
			class="flex min-w-0 flex-1 items-center gap-2 text-left"
			onclick={() => onToggleExpanded(folder.folder_id)}
		>
			{#if expanded}
				<ChevronDownIcon class="text-muted-foreground size-4 shrink-0" />
			{:else}
				<ChevronRightIcon class="text-muted-foreground size-4 shrink-0" />
			{/if}
			<FolderIcon class="text-muted-foreground size-4 shrink-0" />
			<p class="text-foreground truncate text-sm font-medium">{folder.name}</p>
			<span class="text-muted-foreground text-xs">({videoCount})</span>
		</button>
		<Button
			variant="ghost"
			size="icon-xs"
			title="Delete folder"
			onclick={() => onDelete(folder.folder_id)}
		>
			<TrashIcon />
		</Button>
	</Card.Content>
</Card.Root>
