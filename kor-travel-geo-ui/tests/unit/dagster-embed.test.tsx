import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DagsterEmbed } from "@/components/admin/DagsterEmbed";

describe("DagsterEmbed", () => {
  it("URL이 없으면 안내 문구만 표시하고 iframe을 렌더하지 않는다", () => {
    render(<DagsterEmbed url="" />);

    expect(screen.getByText(/Dagster 공개 URL이 구성되지 않았습니다/)).toBeInTheDocument();
    expect(screen.queryByTitle("Dagster 웹서버")).not.toBeInTheDocument();
  });

  it("사용자가 열 때만 sandbox iframe을 만들고 닫으면 제거한다", () => {
    render(<DagsterEmbed url="https://geo-dagster.example.com/" />);

    expect(screen.queryByTitle("Dagster 웹서버")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "콘솔 열기" }));
    const iframe = screen.getByTitle("Dagster 웹서버");
    expect(iframe).toHaveAttribute("src", "https://geo-dagster.example.com/");
    expect(iframe).toHaveAttribute(
      "sandbox",
      "allow-scripts allow-forms allow-popups allow-downloads"
    );
    expect(iframe).toHaveAttribute("referrerpolicy", "no-referrer");
    fireEvent.click(screen.getByRole("button", { name: "콘솔 닫기" }));
    expect(screen.queryByTitle("Dagster 웹서버")).not.toBeInTheDocument();
  });
});
