"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

export interface AdminTabItem<TValue extends string = string> {
  value: TValue;
  label: React.ReactNode;
}

/**
 * admin 표면 공용 탭 셸 (radix Tabs 래핑 — 화살표 키 내비 포함).
 * 기존 수제 탭의 계약을 유지한다: tablist에 aria-label, TabsList에 case-tab-list
 * 클래스(단위 테스트가 toHaveClass로 검증), 탭 접근명은 label 텍스트.
 * 패널은 <AdminTabsContent value=...>로 감싼다 (role=tabpanel 자동).
 */
export function AdminTabs<TValue extends string>({
  label,
  value,
  onValueChange,
  items,
  className,
  children
}: {
  label: string;
  value: TValue;
  onValueChange: (value: TValue) => void;
  items: AdminTabItem<TValue>[];
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Tabs
      value={value}
      onValueChange={(next) => onValueChange(next as TValue)}
      className={className}
    >
      <TabsList aria-label={label} className="case-tab-list">
        {items.map((item) => (
          <TabsTrigger key={item.value} value={item.value}>
            {item.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {children}
    </Tabs>
  );
}

export function AdminTabsContent({
  className,
  ...props
}: React.ComponentProps<typeof TabsContent>) {
  return <TabsContent className={cn("grid gap-4", className)} {...props} />;
}
