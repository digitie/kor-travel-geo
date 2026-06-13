"use client";

import { useReportWebVitals } from "next/web-vitals";

export function WebVitalsReporter() {
  useReportWebVitals((metric) => {
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
