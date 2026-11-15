import { describe, expect, it } from "vitest";
import { joinBase } from "./apiBase";

describe("joinBase", () => {
  it("keeps same-origin paths when no base is set", () => {
    expect(joinBase(undefined, "/api/health")).toBe("/api/health");
    expect(joinBase("", "/api/health")).toBe("/api/health");
  });
  it("prefixes a split-deployment API origin, ignoring trailing slashes and spaces", () => {
    expect(joinBase("https://api.example.org/", "/api/forecast?area=lucknow")).toBe("https://api.example.org/api/forecast?area=lucknow");
    expect(joinBase(" https://api.example.org// ", "/api/cases")).toBe("https://api.example.org/api/cases");
  });
});
