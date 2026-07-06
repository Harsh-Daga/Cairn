import { describe, expect, it } from "vitest";
import { pairLinkConnectors } from "@/lib/spanLinks";

describe("pairLinkConnectors", () => {
  it("pairs retry and handoff links to visible row indices", () => {
    const spanIndex = new Map([
      ["a", 0],
      ["b", 2],
      ["c", 5],
    ]);
    const connectors = pairLinkConnectors(
      [
        { from_span_id: "a", to_span_id: "b", link_type: "retry_of" },
        { from_span_id: "b", to_span_id: "c", link_type: "handoff" },
        { from_span_id: "a", to_span_id: "missing", link_type: "retry_of" },
      ],
      spanIndex,
    );
    expect(connectors).toHaveLength(2);
    expect(connectors[0]).toMatchObject({ fromIndex: 0, toIndex: 2, linkType: "retry_of" });
    expect(connectors[1]).toMatchObject({ fromIndex: 2, toIndex: 5, linkType: "handoff" });
  });
});
