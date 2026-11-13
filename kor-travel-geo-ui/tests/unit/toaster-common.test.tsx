import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, beforeEach } from "vitest";
import { Toast as SharedToast } from "@kor-travel/toast";
import { Toast as OriginalToast } from "radix-ui";
import { Toaster } from "@/components/ui/toaster";
import { toast, useToastStore } from "@/lib/toast";

describe("공통 Toast의 기존 라이브러리 동작", () => {
  beforeEach(() => useToastStore.setState({ toasts: [] }));

  it("원본 Radix namespace 그대로 Provider·Root·swipe·포커스 엔진을 제공한다", () => {
    expect(SharedToast).toBe(OriginalToast);
    for (const name of ["Provider", "Root", "Title", "Description", "Close", "Viewport"] as const)
      expect(SharedToast[name]).toBe(OriginalToast[name]);
  });

  it("기존 store의 내용과 닫기 callback을 유지한다", () => {
    render(<Toaster />);
    act(() => toast.error("저장 실패", "기존 설명"));
    expect(screen.getAllByText("저장 실패").length).toBeGreaterThan(0);
    expect(screen.getAllByText("기존 설명").length).toBeGreaterThan(0);
    expect(useToastStore.getState().toasts[0].duration).toBe(8000);
    fireEvent.click(screen.getByRole("button", { name: "알림 닫기" }));
    expect(useToastStore.getState().toasts).toHaveLength(0);
  });

  it("자동 만료는 새 타이머 없이 Radix Root의 onOpenChange가 처리한다", async () => {
    render(<Toaster />);
    act(() => useToastStore.getState().push({ tone: "info", title: "만료 알림", duration: 40 }));
    expect(screen.getByRole("button", { name: "알림 닫기" })).toBeInTheDocument();
    await waitFor(() => expect(useToastStore.getState().toasts).toHaveLength(0));
  });
});
