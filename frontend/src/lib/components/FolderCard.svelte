<script lang="ts">
	import type { FolderResponse } from '$lib/api-client';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import FolderIcon from '@lucide/svelte/icons/folder';
	import TrashIcon from '@lucide/svelte/icons/trash-2';

	let {
		folder,
		onDrop,
		onDelete
	}: {
		folder: FolderResponse;
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
		<div class="flex min-w-0 items-center gap-2">
			<FolderIcon class="text-muted-foreground size-4 shrink-0" />
			<p class="text-foreground truncate text-sm font-medium">{folder.name}</p>
			<span class="text-muted-foreground text-xs">({folder.video_count})</span>
		</div>
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
