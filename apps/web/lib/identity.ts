// Workspace identity for the local-first deployment.
//
// There is no server-side authentication on this branch: identity is a local
// profile (display name + stable client id) that the backend uses to attribute
// changes, presence, and activity. When hosted OIDC lands, the /bienvenida
// flow is the seam where a real login step replaces completeProfile().

import { setBrowserActor } from "@/lib/collab";

const PROFILE_COMPLETE_KEY = "klave.profileComplete";

export function isProfileComplete(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(PROFILE_COMPLETE_KEY) === "1";
  } catch {
    return true; // Storage unavailable: never trap the user in onboarding.
  }
}

/** Persists the chosen display name and marks onboarding as done. */
export function completeProfile(name: string): void {
  setBrowserActor(name);
  try {
    window.localStorage.setItem(PROFILE_COMPLETE_KEY, "1");
  } catch {}
}
