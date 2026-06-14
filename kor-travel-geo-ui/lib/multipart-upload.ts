import { API_BASE, ApiError, backendPath, postJson } from "@/lib/api";
import type {
  MultipartCompleteRequest,
  MultipartInitiateResponse,
  UploadPartResponse,
  UploadSessionStatus
} from "@/lib/source-files";

export type SlotUploadProgress = {
  slot: string;
  uploadedBytes: number;
  totalBytes: number;
  partsDone: number;
  partsTotal: number;
  state: "idle" | "initiating" | "uploading" | "completing" | "done" | "error";
  error?: string;
};

function uploadPartUrl(
  sessionId: string,
  slotId: string,
  partNumber: number,
  multipartUploadId: string
): string {
  const path = `/admin/source-files/upload-sessions/${sessionId}/files/${slotId}/multipart/${partNumber}?multipart_upload_id=${encodeURIComponent(
    multipartUploadId
  )}`;
  return `${API_BASE}${backendPath(path)}`;
}

/**
 * Upload a single slot's file as a resumable multipart upload.
 *
 * Drives the T-202 endpoints: initiate → PUT each part → complete. Reports
 * per-part progress through ``onProgress`` so the UI can render a progress bar.
 */
export async function uploadSlotFile({
  sessionId,
  slotId,
  file,
  partSizeBytes,
  onProgress,
  signal
}: {
  sessionId: string;
  slotId: string;
  file: File;
  partSizeBytes: number;
  onProgress?: (progress: SlotUploadProgress) => void;
  signal?: AbortSignal;
}): Promise<UploadSessionStatus> {
  const partSize = partSizeBytes > 0 ? partSizeBytes : 8 * 1024 * 1024;
  const partsTotal = Math.max(1, Math.ceil(file.size / partSize));

  const report = (patch: Partial<SlotUploadProgress>) =>
    onProgress?.({
      slot: slotId,
      uploadedBytes: 0,
      totalBytes: file.size,
      partsDone: 0,
      partsTotal,
      state: "uploading",
      ...patch
    });

  report({ state: "initiating" });
  const initiate = await postJson<MultipartInitiateResponse>(
    `/admin/source-files/upload-sessions/${sessionId}/files/${slotId}/multipart`,
    {}
  );
  const multipartUploadId = initiate.multipart_upload_id;

  const partEtags: [number, string][] = [];
  let uploadedBytes = 0;
  for (let index = 0; index < partsTotal; index += 1) {
    if (signal?.aborted) {
      throw new ApiError(0, "업로드가 취소되었습니다");
    }
    const partNumber = index + 1;
    const start = index * partSize;
    const blob = file.slice(start, start + partSize);
    const response = await fetch(
      uploadPartUrl(sessionId, slotId, partNumber, multipartUploadId),
      {
        method: "PUT",
        body: blob,
        headers: { "content-type": "application/octet-stream" },
        signal
      }
    );
    if (!response.ok) {
      const text = await response.text();
      report({ state: "error", error: text, uploadedBytes, partsDone: index });
      throw new ApiError(response.status, text || `${response.status} part upload failed`);
    }
    const part = (await response.json()) as UploadPartResponse;
    partEtags.push([part.part_number, part.part_etag]);
    uploadedBytes += blob.size;
    report({ state: "uploading", uploadedBytes, partsDone: partNumber });
  }

  report({ state: "completing", uploadedBytes, partsDone: partsTotal });
  const completeBody: MultipartCompleteRequest = { part_etags: partEtags };
  const session = await fetch(
    `${API_BASE}${backendPath(
      `/admin/source-files/upload-sessions/${sessionId}/files/${slotId}/multipart/complete?multipart_upload_id=${encodeURIComponent(
        multipartUploadId
      )}`
    )}`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(completeBody)
    }
  );
  if (!session.ok) {
    const text = await session.text();
    report({ state: "error", error: text, uploadedBytes, partsDone: partsTotal });
    throw new ApiError(session.status, text || "multipart complete failed");
  }
  report({ state: "done", uploadedBytes, partsDone: partsTotal });
  return (await session.json()) as UploadSessionStatus;
}
