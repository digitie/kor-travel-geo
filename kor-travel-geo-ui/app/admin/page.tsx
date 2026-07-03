import type { Metadata } from "next";

import { AdminHome } from "@/components/admin/AdminHome";
import { PageHeader } from "@/components/ui/PageHeader";
import { ADMIN_PAGES } from "@/lib/admin-pages";

export const metadata: Metadata = {
  title: ADMIN_PAGES.home.title,
  description: ADMIN_PAGES.home.description
};

export default function AdminPage() {
  return (
    <>
      <PageHeader
        title={ADMIN_PAGES.home.title}
        description={ADMIN_PAGES.home.description}
      />
      <AdminHome />
    </>
  );
}
