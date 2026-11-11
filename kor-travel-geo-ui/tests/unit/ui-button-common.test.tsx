// SPDX-License-Identifier: GPL-3.0-or-later
// SPDX-FileCopyrightText: 2026 Youn-sok Choi (digitie)
import { createRef, type ComponentProps, type ComponentType, type FormEvent } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Button as CommonButton } from "@kor-travel/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@kor-travel/ui/dialog";
import { Button } from "@/components/ui/button";

// 이전 Geo 타입도 같은 실행 fixture에서 확인할 수 있도록 공통 공개 계약으로 검사한다.
const Subject = Button as ComponentType<ComponentProps<typeof CommonButton>>;

describe("Geo 공통 Button 소비 계약", () => {
  it("진행 중에는 포커스를 보존하고 활성화를 차단한다", async () => {
    const click = vi.fn();
    render(<Subject loading onClick={click}>저장</Subject>);
    const button = screen.getByRole("button", { name: "저장" });
    button.focus();
    fireEvent.click(button);
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).toHaveFocus();
    expect(click).not.toHaveBeenCalled();
  });

  it("비활성화 이유를 공통 title 계약으로 제공한다", () => {
    render(<Subject disabled disabledReason="선택한 자료가 없습니다">실행</Subject>);
    const button = screen.getByRole("button", { name: "실행" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", "선택한 자료가 없습니다");
  });

  it("기본 동작은 폼을 제출하지 않고 명시적 submit만 제출한다", async () => {
    const submit = vi.fn((event: FormEvent) => event.preventDefault());
    render(<form onSubmit={submit}><Button>다른 동작</Button><Button type="submit">제출</Button></form>);
    fireEvent.click(screen.getByRole("button", { name: "다른 동작" }));
    expect(submit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "제출" }));
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it("asChild 링크의 의미와 variant/size를 유지한다", () => {
    render(<Button asChild variant="link" size="sm"><a href="/manual">도움말</a></Button>);
    const link = screen.getByRole("link", { name: "도움말" });
    expect(link).toHaveAttribute("href", "/manual");
    expect(link).not.toHaveAttribute("type");
    expect(link).toHaveAttribute("data-variant", "link");
    expect(link).toHaveAttribute("data-size", "sm");
  });

  it("React19 ref와 Radix trigger의 열기·Escape·포커스 복귀를 유지한다", async () => {
    const ref = createRef<HTMLButtonElement>();
    render(<Dialog><DialogTrigger asChild><Button ref={ref}>상세 열기</Button></DialogTrigger>
      <DialogContent><DialogTitle>상세</DialogTitle><DialogDescription>자료 상세</DialogDescription></DialogContent>
    </Dialog>);
    const opener = screen.getByRole("button", { name: "상세 열기" });
    expect(ref.current).toBe(opener);
    fireEvent.click(opener);
    expect(await screen.findByRole("dialog", { name: "상세" })).toBeVisible();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(opener).toHaveFocus());
  });
});
