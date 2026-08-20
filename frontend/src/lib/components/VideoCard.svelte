<script lang="ts">
	import type { VideoResponse } from '$lib/api-client';
	import * as Card from '$lib/components/ui/card/index.js';
	import { Checkbox } from '$lib/components/ui/checkbox/index.js';
	import { Button } from '$lib/components/ui/button/index.js';
	import DownloadIcon from '@lucide/svelte/icons/download';

	let {
		video,
		selected,
		onToggleSelect,
		onDragStart
	}: {
		video: VideoResponse;
		selected: boolean;
		onToggleSelect: (videoId: string) => void;
		onDragStart: (videoId: string, event: DragEvent) => void;
	} = $props();
</script>

<Card.Root
	class={selected ? 'ring-2 ring-sky-400' : ''}
	draggable="true"
	ondragstart={(e: DragEvent) => onDragStart(video.video_id, e)}
>
	<Card.Content class="flex flex-col gap-2">
		<div class="flex items-start gap-2">
			<Checkbox
				checked={selected}
				onCheckedChange={() => onToggleSelect(video.video_id)}
				class="mt-0.5"
			/>
			<div class="min-w-0 flex-1">
				<p class="text-foreground truncate text-sm font-medium">{video.display_name}</p>
				<p class="text-muted-foreground text-xs">Profile: {video.profile}</p>
			</div>
		</div>
		<Button href={video.result_url} download size="sm" variant="outline" class="w-fit">
			<DownloadIcon />
			Download
		</Button>
	</Card.Content>
</Card.Root>
