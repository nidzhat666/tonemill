import { api, type FolderResponse, type VideoResponse } from '$lib/api-client';
import { SvelteSet } from 'svelte/reactivity';

class LibraryStore {
	videos = $state<VideoResponse[]>([]);
	folders = $state<FolderResponse[]>([]);
	selectedVideoIds = $state(new SvelteSet<string>());
	/** Client-local display state only (FR-013, FR-015; research.md #6) -- never sent to or
	 * read from the backend, and reset every time the library is (re)loaded.
	 */
	expandedFolderIds = $state(new SvelteSet<string>());
	/** Unsorted defaults open, independent of named folders (spec.md Assumptions). */
	unsortedExpanded = $state(true);

	async load(): Promise<void> {
		const [videos, folders] = await Promise.all([api.listVideos(), api.listFolders()]);
		this.videos = videos;
		this.folders = folders;
	}

	unsortedVideos(): VideoResponse[] {
		return this.videos.filter((v) => v.folder_id === null);
	}

	videosInFolder(folderId: string): VideoResponse[] {
		return this.videos.filter((v) => v.folder_id === folderId);
	}

	isSelected(videoId: string): boolean {
		return this.selectedVideoIds.has(videoId);
	}

	toggleSelected(videoId: string): void {
		if (this.selectedVideoIds.has(videoId)) this.selectedVideoIds.delete(videoId);
		else this.selectedVideoIds.add(videoId);
	}

	clearSelection(): void {
		this.selectedVideoIds.clear();
	}

	isFolderExpanded(folderId: string): boolean {
		return this.expandedFolderIds.has(folderId);
	}

	toggleFolderExpanded(folderId: string): void {
		if (this.expandedFolderIds.has(folderId)) this.expandedFolderIds.delete(folderId);
		else this.expandedFolderIds.add(folderId);
	}

	async createFolder(name: string): Promise<FolderResponse> {
		const folder = await api.createFolder(name);
		this.folders.push(folder);
		return folder;
	}

	/** The folder itself is deleted; every video it held reverts to unsorted (FR-015) --
	 * mirrored locally so the grid updates without a full re-fetch.
	 */
	async deleteFolder(folderId: string): Promise<void> {
		await api.deleteFolder(folderId);
		this.folders = this.folders.filter((f) => f.folder_id !== folderId);
		this.videos = this.videos.map((v) =>
			v.folder_id === folderId ? { ...v, folder_id: null } : v
		);
	}

	/** Moves the given videos (or the current selection, if `videoIds` is omitted) into
	 * `folderId` (or unsorted, if null) -- covers both single drag-and-drop and multi-select
	 * bulk move with one call (FR-010, FR-011, FR-014).
	 */
	async moveVideos(folderId: string | null, videoIds?: string[]): Promise<void> {
		const ids = videoIds ?? [...this.selectedVideoIds];
		if (ids.length === 0) return;
		await api.moveVideos(ids, folderId);
		this.videos = this.videos.map((v) =>
			ids.includes(v.video_id) ? { ...v, folder_id: folderId } : v
		);
		this.clearSelection();
	}

	/** Permanently deletes the given videos (or the current selection, if `videoIds` is
	 * omitted) -- irreversible (FR-021). Mirrors `moveVideos`'s shape: call the API, then
	 * reflect the outcome locally without a full re-fetch.
	 */
	async deleteVideos(videoIds?: string[]): Promise<void> {
		const ids = videoIds ?? [...this.selectedVideoIds];
		if (ids.length === 0) return;
		await api.deleteVideos(ids);
		this.videos = this.videos.filter((v) => !ids.includes(v.video_id));
		this.clearSelection();
	}
}

export const libraryStore = new LibraryStore();
