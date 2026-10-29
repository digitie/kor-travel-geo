import { Agent, Dispatcher1Wrapper } from "undici";

// 원천 묶음은 응답 헤더를 만들기 전에 수 GB를 내려받아 검사·해시한다.
// Node 기본 fetch의 Dispatcher v1 계약으로 Undici 8 Agent를 연결한다.
const sourceArchiveDispatcher = new Dispatcher1Wrapper(
  new Agent({ headersTimeout: 30 * 60_000 })
);
const SOURCE_ARCHIVE_OPERATION = /^v1\/admin\/(?:source-files\/(?:upload-sessions\/[^/]+\/(?:preview-validate|register)|groups\/[^/]+\/revalidate)|source-match-sets\/[^/]+\/run-validation)$/;

export function sourceArchiveDispatcherFor(method: string, path: string[]) {
  return method === "POST" && SOURCE_ARCHIVE_OPERATION.test(path.join("/"))
    ? sourceArchiveDispatcher
    : undefined;
}
