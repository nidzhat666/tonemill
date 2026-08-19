import { api, type CompletedPart } from './api-client';

export interface UploadProgress {
	uploadedBytes: number;
	totalBytes: number;
	percent: number;
}

export interface UploadSession {
	uploadId: string;
	s3Key: string;
	partSizeBytes: number;
	partCount: number;
}

const CONCURRENCY = 4;

async function uploadPart(
	uploadId: string,
	partNumber: number,
	chunk: Blob
): Promise<CompletedPart> {
	const { upload_url } = await api.getPartUploadUrl(uploadId, partNumber);
	const response = await fetch(upload_url, { method: 'PUT', body: chunk });
	if (!response.ok) {
		throw new Error(`part ${partNumber} upload failed: ${response.status}`);
	}
	const etag = response.headers.get('ETag') ?? response.headers.get('etag');
	if (!etag) throw new Error(`part ${partNumber} upload succeeded but no ETag was returned`);
	return { part_number: partNumber, etag };
}

/** Start a brand-new resumable multipart upload (FR-001, FR-030, FR-031). */
export async function startUpload(file: File): Promise<UploadSession> {
	const initiated = await api.initiateUpload(file.name, file.type, file.size);
	return {
		uploadId: initiated.upload_id,
		s3Key: initiated.s3_key,
		partSizeBytes: initiated.part_size_bytes,
		partCount: initiated.part_count
	};
}

/**
 * Upload (or resume uploading) a file against an existing session. Parts already received
 * are discovered via GET /uploads/{id}/parts (FR-034) -- never assumed from local state
 * alone, so resume works even after a lost session (browser closed, new device).
 */
export async function uploadFile(
	file: File,
	session: UploadSession,
	onProgress?: (progress: UploadProgress) => void
): Promise<string> {
	const { parts: alreadyReceived } = await api.listReceivedParts(session.uploadId);
	const completed = new Map<number, CompletedPart>(
		alreadyReceived.map((p) => [p.part_number, { part_number: p.part_number, etag: p.etag }])
	);

	const remaining: number[] = [];
	for (let partNumber = 1; partNumber <= session.partCount; partNumber++) {
		if (!completed.has(partNumber)) remaining.push(partNumber);
	}

	const report = () => {
		if (!onProgress) return;
		const uploadedBytes = completed.size * session.partSizeBytes;
		const totalBytes = file.size;
		onProgress({
			uploadedBytes: Math.min(uploadedBytes, totalBytes),
			totalBytes,
			percent: Math.min(100, (completed.size / session.partCount) * 100)
		});
	};
	report();

	let cursor = 0;
	async function worker(): Promise<void> {
		while (cursor < remaining.length) {
			const partNumber = remaining[cursor++];
			const start = (partNumber - 1) * session.partSizeBytes;
			const end = Math.min(start + session.partSizeBytes, file.size);
			const chunk = file.slice(start, end);
			const result = await uploadPart(session.uploadId, partNumber, chunk);
			completed.set(partNumber, result);
			report();
		}
	}
	await Promise.all(Array.from({ length: Math.min(CONCURRENCY, remaining.length) }, worker));

	const orderedParts = Array.from(completed.values()).sort((a, b) => a.part_number - b.part_number);
	await api.completeUpload(session.uploadId, orderedParts);
	return session.s3Key;
}
