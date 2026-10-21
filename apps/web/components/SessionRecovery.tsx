"use client";

import { useEffect, useRef } from "react";
import { useRouter, usePathname } from "next/navigation";
import { safeReturnPath, SESSION_RETURN_KEY } from "@/lib/sessionReturn";

export function SessionRecovery() {
  const router = useRouter();
  const pathname = usePathname();
  const redirecting = useRef(false);
  useEffect(() => { redirecting.current = false; }, [pathname]);
  useEffect(() => {
    function recover() {
      if (redirecting.current || pathname === "/bienvenida") return;
      redirecting.current = true;
      const destination = safeReturnPath(
        window.location.pathname + window.location.search + window.location.hash,
        window.location.origin,
      );
      try { sessionStorage.setItem(SESSION_RETURN_KEY, destination); } catch {}
      router.replace("/bienvenida?reason=session_expired");
    }
    window.addEventListener("klave:session-expired", recover);
    return () => window.removeEventListener("klave:session-expired", recover);
  }, [pathname, router]);
  return null;
}
