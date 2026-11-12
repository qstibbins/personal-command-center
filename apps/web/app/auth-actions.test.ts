import { beforeEach, describe, expect, it, vi } from "vitest";

const signOutMock = vi.fn();

vi.mock("../auth", () => ({
  signOut: (...args: unknown[]) => signOutMock(...args),
}));

import { signOutAction } from "./auth-actions";

describe("signOutAction", () => {
  beforeEach(() => {
    signOutMock.mockReset();
    signOutMock.mockResolvedValue(undefined);
  });

  it("calls Auth.js signOut with redirect to /signin (revokes DB session)", async () => {
    await signOutAction();
    expect(signOutMock).toHaveBeenCalledTimes(1);
    expect(signOutMock).toHaveBeenCalledWith({ redirectTo: "/signin" });
  });
});
