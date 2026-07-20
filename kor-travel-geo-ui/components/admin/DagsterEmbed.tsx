"use client";

import { ExternalLink } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/Panel";

/**
 * 관리자 화면에 Dagster 웹서버(run/launchpad/schedule 콘솔)를 iframe으로 임베드한다.
 * URL은 백엔드 `KTG_DAGSTER_PUBLIC_URL`(geo-dagster 공개 도메인)을 서버측에서 해석해
 * prop으로 받는다. 값이 없으면 안내만 노출하고 iframe은 렌더하지 않는다.
 * 백엔드 GraphQL(내부 `dagster_url`, SSRF-allowlist)과는 별개의 브라우저용 URL이다.
 */
export function DagsterEmbed({ url }: { url: string }) {
  const target = url.trim();

  if (!target) {
    return (
      <Panel
        title="Dagster 콘솔"
        description="실행 오케스트레이션 웹서버(run/launchpad/schedule)"
      >
        <p className="m-0 text-sm text-muted-foreground">
          Dagster 공개 URL이 구성되지 않았습니다. 배포 환경에{" "}
          <code>KTG_DAGSTER_PUBLIC_URL</code>을 설정하면 이 화면에 콘솔이 임베드됩니다.
        </p>
      </Panel>
    );
  }

  return (
    <Panel
      title="Dagster 콘솔"
      description="실행 오케스트레이션 웹서버(run/launchpad/schedule)를 관리자 화면에 임베드"
      actions={
        <Button asChild variant="outline" size="sm">
          <a href={target} target="_blank" rel="noopener noreferrer">
            <ExternalLink className="mr-1.5 h-4 w-4" aria-hidden />
            새 탭에서 열기
          </a>
        </Button>
      }
    >
      <iframe
        src={target}
        title="Dagster 웹서버"
        referrerPolicy="no-referrer"
        sandbox="allow-scripts allow-forms allow-popups allow-downloads allow-same-origin"
        className="h-[760px] w-full rounded-md border bg-background"
      />
    </Panel>
  );
}
