import type { Metadata } from "next";

import { DagsterEmbed } from "@/components/admin/DagsterEmbed";
import { DagsterPanel } from "@/components/admin/DagsterPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";
import { resolveDagsterPublicUrl } from "@/lib/runtime-config";

export const metadata: Metadata = {
  title: ADMIN_PAGES.dagster.title,
  description: ADMIN_PAGES.dagster.description
};

// Read the runtime KTG_DAGSTER_PUBLIC_URL per request (not baked at build time).
export const dynamic = "force-dynamic";

function managerOrigin(): string | null {
  const value = process.env.KTG_DOCKER_MANAGER_UI_URL;
  if (!value) return null;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) && !url.username && !url.password
      ? url.origin : null;
  } catch {
    return null;
  }
}

export default function DagsterPage() {
  const dagsterUrl = resolveDagsterPublicUrl();
  return (
    <>
      <PageHeader
        title={ADMIN_PAGES.dagster.title}
        description={ADMIN_PAGES.dagster.description}
      />
      <DagsterPanel managerOrigin={managerOrigin()} />
      <DagsterEmbed url={dagsterUrl} />
    </>
  );
}
