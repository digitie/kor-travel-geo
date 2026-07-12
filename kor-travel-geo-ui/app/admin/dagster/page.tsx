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

export default function DagsterPage() {
  const dagsterUrl = resolveDagsterPublicUrl();
  return (
    <>
      <PageHeader
        title={ADMIN_PAGES.dagster.title}
        description={ADMIN_PAGES.dagster.description}
      />
      <DagsterPanel />
      <DagsterEmbed url={dagsterUrl} />
    </>
  );
}
