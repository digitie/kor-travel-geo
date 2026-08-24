"use client";

import { useReportWebVitals } from "next/web-vitals";

export function WebVitalsReporter() {
  useReportWebVitals((metric) => {
    // /api/metrics/* requires a session; beaconing from the unauthenticated login page only
    // produced 401 console noise (issue #515).
    //
    // Read from `location` rather than `usePathname()`: useReportWebVitals re-subscribes
    // whenever the callback identity changes and never unsubscribes, so a hook that re-renders
    // this component would stack duplicate subscriptions, each holding a stale pathname. This
    // also keeps the gate and the reported `route` reading the same value.
    if (window.location.pathname === "/login") {
      return;
    }
    const payload = JSON.stringify({
      name: metric.name,
      rating: metric.rating,
      value: metric.value,
      route: window.location.pathname
    });
    if (navigator.sendBeacon) {
      navigator.sendBeacon(
        "/api/metrics/web-vitals",
        new Blob([payload], { type: "application/json" })
      );
      return;
    }
    void fetch("/api/metrics/web-vitals", {
      method: "POST",
      body: payload,
      headers: { "content-type": "application/json" },
      keepalive: true
    });
  });
  return null;
}
