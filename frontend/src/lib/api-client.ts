// Typed client for the Tonemill API, per contracts/api.md. All calls go through the
// same-origin /api/* backend-for-frontend proxy (src/routes/api/[...path]/+server.ts) --
// never directly at the API's internal address.

export interface InitiateUploadResponse {
	upload_id: string;
	s3_key: string;
	part_size_bytes: number;
	part_count: number;
}

export interface PartUrlResponse {
	part_number: number;
	upload_url: string;
}

export interface PartInfo {
	part_number: number;
	etag: string;
	size_bytes: number;
}

export interface CompletedPart {
	part_number: number;
	etag: string;
}

export interface ProfileInfo {
	name: string;
	source_format: string;
	execution_path: 'gpu' | 'cpu' | null;
	implemented: boolean;
}

export type JobStatus = 'queued' | 'running' | 'done' | 'failed';
export type JobStage = 'downloading' | 'processing' | 'uploading_result' | null;

export interface JobStatusResponse {
	job_id: string;
	source_key: string;
	status: JobStatus;
	stage: JobStage;
	progress_pct: number;
	requested_profile: string;
	resolved_profile: string | null;
	max_quality: boolean;
	result_url: string | null;
	error: string | null;
}

export interface VideoResponse {
	video_id: string;
	display_name: string;
	profile: string;
	recorded_created_at: string;
	folder_id: string | null;
	result_url: string;
	thumbnail_url: string | null;
	preview_clip_urls: string[];
}

export interface FolderResponse {
	folder_id: string;
	name: string;
	video_count: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
	const response = await fetch(`/api${path}`, {
		...init,
		headers: { 'content-type': 'application/json', ...init?.headers }
	});
	if (!response.ok) {
		let detail = response.statusText;
		try {
			const body = await response.json();
			detail = body.detail ?? detail;
		} catch {
			// non-JSON error body; fall back to statusText
		}
		// No numeric status prefix in the message itself -- callers display error.message
		// directly to the user (e.g. FR-022's friendly duplicate-submission rejection), who
		// shouldn't have to parse an HTTP status code to understand what happened.
		throw new Error(detail);
	}
	if (response.status === 204) return undefined as T;
	return (await response.json()) as T;
}

export const api = {
	initiateUpload(filename: string, contentType: string, sizeBytes: number) {
		return request<InitiateUploadResponse>('/uploads', {
			method: 'POST',
			body: JSON.stringify({ filename, content_type: contentType, size_bytes: sizeBytes })
		});
	},

	getPartUploadUrl(uploadId: string, partNumber: number) {
		return request<PartUrlResponse>(`/uploads/${uploadId}/parts/${partNumber}`, {
			method: 'POST'
		});
	},

	listReceivedParts(uploadId: string) {
		return request<{ parts: PartInfo[] }>(`/uploads/${uploadId}/parts`);
	},

	completeUpload(uploadId: string, parts: CompletedPart[]) {
		return request<{ s3_key: string; status: string }>(`/uploads/${uploadId}/complete`, {
			method: 'POST',
			body: JSON.stringify({ parts })
		});
	},

	abortUpload(uploadId: string) {
		return request<void>(`/uploads/${uploadId}/abort`, { method: 'POST' });
	},

	listProfiles() {
		return request<ProfileInfo[]>('/profiles');
	},

	submitJob(s3Key: string, profile: string, maxQuality: boolean) {
		return request<{ job_id: string; status: JobStatus }>('/jobs', {
			method: 'POST',
			body: JSON.stringify({ s3_key: s3Key, profile, max_quality: maxQuality })
		});
	},

	getJobStatus(jobId: string) {
		return request<JobStatusResponse>(`/jobs/${jobId}`);
	},

	listJobs() {
		return request<JobStatusResponse[]>('/jobs');
	},

	dismissJob(jobId: string) {
		return request<void>(`/jobs/${jobId}/dismiss`, { method: 'POST' });
	},

	dismissAllJobs() {
		return request<{ dismissed: number }>('/jobs/dismiss-all', { method: 'POST' });
	},

	listVideos() {
		return request<VideoResponse[]>('/videos');
	},

	moveVideos(videoIds: string[], folderId: string | null) {
		return request<{ moved: number }>('/videos/move', {
			method: 'POST',
			body: JSON.stringify({ video_ids: videoIds, folder_id: folderId })
		});
	},

	listFolders() {
		return request<FolderResponse[]>('/folders');
	},

	createFolder(name: string) {
		return request<FolderResponse>('/folders', {
			method: 'POST',
			body: JSON.stringify({ name })
		});
	},

	deleteFolder(folderId: string) {
		return request<void>(`/folders/${folderId}`, { method: 'DELETE' });
	},

	deleteVideos(videoIds: string[]) {
		return request<{ deleted: number }>('/videos/delete', {
			method: 'POST',
			body: JSON.stringify({ video_ids: videoIds })
		});
	}
};
