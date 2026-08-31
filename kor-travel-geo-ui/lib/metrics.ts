type Labels = Record<string, string>;

type CounterSample = {
  labels: Labels;
  value: number;
};

type HistogramSample = {
  labels: Labels;
  buckets: number[];
  count: number;
  sum: number;
};

const REQUEST_DURATION_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10];
const WEB_VITAL_BUCKETS = [
  0.001,
  0.005,
  0.01,
  0.025,
  0.05,
  0.1,
  0.25,
  0.5,
  1,
  2.5,
  5,
  10,
  100,
  1_000,
  10_000
];
const METRIC_HTTP_METHODS = new Set([
  "GET",
  "POST",
  "PUT",
  "PATCH",
  "DELETE",
  "HEAD",
  "OPTIONS"
]);
const WEB_VITAL_NAMES = new Set(["CLS", "FCP", "FID", "INP", "LCP", "TTFB"]);
const WEB_VITAL_RATINGS = new Set(["good", "needs-improvement", "poor"]);
const WEB_VITAL_STATIC_ROUTES = new Set([
  "/admin",
  "/admin/backups",
  "/admin/cache",
  "/admin/consistency",
  "/admin/dagster",
  "/admin/files",
  "/admin/load",
  "/admin/logs",
  "/admin/ops",
  "/admin/settings",
  "/admin/source-files",
  "/admin/tables",
  "/debug/explain",
  "/debug/geocode",
  "/debug/normalize",
  "/debug/reverse"
]);

class CounterMetric {
  private readonly samples = new Map<string, CounterSample>();

  constructor(
    readonly name: string,
    readonly help: string,
    readonly labelNames: string[]
  ) {}

  inc(labels: Labels, amount = 1): void {
    const sample = this.sample(labels);
    sample.value += amount;
  }

  render(): string[] {
    return [
      `# HELP ${this.name} ${this.help}`,
      `# TYPE ${this.name} counter`,
      ...Array.from(this.samples.values()).map(
        (sample) => `${this.name}${renderLabels(sample.labels)} ${sample.value}`
      )
    ];
  }

  private sample(labels: Labels): CounterSample {
    const normalized = normalizeLabels(this.labelNames, labels);
    const key = keyForLabels(normalized);
    const existing = this.samples.get(key);
    if (existing) {
      return existing;
    }
    const sample = { labels: normalized, value: 0 };
    this.samples.set(key, sample);
    return sample;
  }
}

class HistogramMetric {
  private readonly samples = new Map<string, HistogramSample>();

  constructor(
    readonly name: string,
    readonly help: string,
    readonly labelNames: string[],
    readonly buckets: number[]
  ) {}

  observe(labels: Labels, value: number): void {
    const sample = this.sample(labels);
    sample.count += 1;
    sample.sum += value;
    this.buckets.forEach((bucket, index) => {
      if (value <= bucket) {
        sample.buckets[index] += 1;
      }
    });
  }

  render(): string[] {
    const lines = [`# HELP ${this.name} ${this.help}`, `# TYPE ${this.name} histogram`];
    for (const sample of this.samples.values()) {
      this.buckets.forEach((bucket, index) => {
        lines.push(
          `${this.name}_bucket${renderLabels({ ...sample.labels, le: String(bucket) })} ${
            sample.buckets[index]
          }`
        );
      });
      lines.push(
        `${this.name}_bucket${renderLabels({ ...sample.labels, le: "+Inf" })} ${sample.count}`
      );
      lines.push(`${this.name}_sum${renderLabels(sample.labels)} ${sample.sum}`);
      lines.push(`${this.name}_count${renderLabels(sample.labels)} ${sample.count}`);
    }
    return lines;
  }

  private sample(labels: Labels): HistogramSample {
    const normalized = normalizeLabels(this.labelNames, labels);
    const key = keyForLabels(normalized);
    const existing = this.samples.get(key);
    if (existing) {
      return existing;
    }
    const sample = {
      labels: normalized,
      buckets: this.buckets.map(() => 0),
      count: 0,
      sum: 0
    };
    this.samples.set(key, sample);
    return sample;
  }
}

const uiRequests = new CounterMetric(
  "kor_travel_geo_ui_http_requests_total",
  "Next.js admin UI route handler requests by route, method, and status code.",
  ["method", "route", "status_code"]
);

const uiRequestDuration = new HistogramMetric(
  "kor_travel_geo_ui_http_request_duration_seconds",
  "Next.js admin UI route handler duration in seconds.",
  ["method", "route", "status_code"],
  REQUEST_DURATION_BUCKETS
);

const proxyUpstreamDuration = new HistogramMetric(
  "kor_travel_geo_ui_proxy_upstream_request_duration_seconds",
  "Next.js admin UI backend proxy upstream fetch duration in seconds.",
  ["method", "backend_route", "status_code"],
  REQUEST_DURATION_BUCKETS
);

const webVitals = new HistogramMetric(
  "kor_travel_geo_ui_web_vital_value",
  "Browser Web Vitals values reported by the admin UI. Units follow each Web Vital metric.",
  ["name", "route", "rating"],
  WEB_VITAL_BUCKETS
);

const webVitalsTotal = new CounterMetric(
  "kor_travel_geo_ui_web_vitals_total",
  "Browser Web Vitals samples reported by metric name, route, and rating.",
  ["name", "route", "rating"]
);

export function recordUiRequest(input: {
  method: string;
  route: string;
  statusCode: number;
  elapsedSeconds: number;
}): void {
  const labels = {
    method: normalizeMetricMethod(input.method),
    route: normalizeMetricRoute(input.route),
    status_code: String(input.statusCode)
  };
  uiRequests.inc(labels);
  uiRequestDuration.observe(labels, input.elapsedSeconds);
}

export function recordProxyUpstream(input: {
  method: string;
  backendRoute: string;
  statusCode: number;
  elapsedSeconds: number;
}): void {
  proxyUpstreamDuration.observe(
    {
      method: normalizeMetricMethod(input.method),
      backend_route: normalizeMetricRoute(input.backendRoute),
      status_code: String(input.statusCode)
    },
    input.elapsedSeconds
  );
}

export function recordWebVital(input: {
  name: string;
  route: string;
  rating: string;
  value: number;
}): boolean {
  if (!Number.isFinite(input.value) || input.value < 0) {
    return false;
  }
  const labels = {
    name: WEB_VITAL_NAMES.has(input.name) ? input.name : "other",
    route: normalizeWebVitalRoute(input.route),
    rating: WEB_VITAL_RATINGS.has(input.rating) ? input.rating : "unknown"
  };
  webVitalsTotal.inc(labels);
  webVitals.observe(labels, input.value);
  return true;
}

export function backendRouteForMetrics(pathSegments: string[]): string {
  return normalizeMetricRoute(`/${pathSegments.join("/")}`);
}

export function normalizeMetricRoute(path: string): string {
  const parts = path.split("/").filter(Boolean);
  return `/${parts.map(normalizeMetricSegment).join("/") || "root"}`;
}

export function renderPrometheusMetrics(): string {
  return [
    ...uiRequests.render(),
    ...uiRequestDuration.render(),
    ...proxyUpstreamDuration.render(),
    ...webVitalsTotal.render(),
    ...webVitals.render(),
    ""
  ].join("\n");
}

function normalizeMetricSegment(segment: string): string {
  if (/^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(segment)) {
    return ":id";
  }
  if (/^\d+$/.test(segment)) {
    return ":id";
  }
  if (segment.length > 32 && /^[A-Za-z0-9_-]+$/.test(segment)) {
    return ":id";
  }
  return segment;
}

function normalizeMetricMethod(method: string): string {
  const normalized = method.toUpperCase();
  return METRIC_HTTP_METHODS.has(normalized) ? normalized : "other";
}

function normalizeWebVitalRoute(path: string): string {
  const normalized = normalizeMetricRoute(path);
  if (WEB_VITAL_STATIC_ROUTES.has(normalized)) {
    return normalized;
  }
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length === 3 && parts[0] === "admin" && parts[1] === "consistency") {
    return "/admin/consistency/:id";
  }
  // Web Vitals arrive from a browser pathname. Keep only the known app pages so a crafted
  // pathname cannot create one time series per arbitrary URL.
  return "/other";
}

function normalizeLabels(labelNames: string[], labels: Labels): Labels {
  return Object.fromEntries(labelNames.map((name) => [name, labels[name] ?? "unknown"]));
}

function keyForLabels(labels: Labels): string {
  return JSON.stringify(labels);
}

function renderLabels(labels: Labels): string {
  const entries = Object.entries(labels);
  if (entries.length === 0) {
    return "";
  }
  return `{${entries.map(([key, value]) => `${key}="${escapeLabel(value)}"`).join(",")}}`;
}

function escapeLabel(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/"/g, '\\"');
}
