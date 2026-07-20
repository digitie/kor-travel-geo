import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DagsterEmbed } from "@/components/admin/DagsterEmbed";

describe("DagsterEmbed", () => {
  it("URL이 없으면 안내 문구만 표시하고 iframe을 렌더하지 않는다", () => {
    render(<DagsterEmbed url="" />);

    expect(screen.getByText(/Dagster 공개 URL이 구성되지 않았습니다/)).toBeInTheDocument();
    expect(screen.queryByTitle("Dagster 웹서버")).not.toBeInTheDocument();
  });

  it("URL이 있으면 sandbox가 걸린 iframe으로 임베드한다", () => {
    render(<DagsterEmbed url="https://geo-dagster.example.com/" />);

    const iframe = screen.getByTitle("Dagster 웹서버");
    expect(iframe).toHaveAttribute("src", "https://geo-dagster.example.com/");
    expect(iframe).toHaveAttribute(
      "sandbox",
      "allow-scripts allow-forms allow-popups allow-downloads allow-same-origin"
    );
    expect(iframe).toHaveAttribute("referrerpolicy", "no-referrer");
  });
});
