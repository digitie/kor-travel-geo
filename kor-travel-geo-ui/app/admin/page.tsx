import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Admin",
  description: "관리 라우트 기본 진입점"
};

export default function AdminPage() {
  redirect("/debug/geocode");
}
