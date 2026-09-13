/**
 * OpenTelemetry Web + web-vitals для Knowledge Map.
 *
 * - WebTracerProvider с OTLP/HTTP экспортером (Alloy через nginx/vite-прокси);
 * - instrumenting fetch: автop traceparent + метрика длительности запроса;
 * - web-vitals (LCP/FCP/INP/TTFB, CLS);
 * - счётчик ошибок страницы;
 * - session_id (X-Client-Session-ID) → API.
 *
 * Управление:
 * - `VITE_OTEL_ENABLED=false` — полностью выключить;
 * - `VITE_OTEL_COLLECTOR_URL` — явный адрес коллектора (например
 *   "https://collector.example", иначе — same-origin "/v1/traces").
 */

import {
  metrics,
} from '@opentelemetry/api';
import { Resource } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME } from '@opentelemetry/semantic-conventions';
import { BatchSpanProcessor } from '@opentelemetry/sdk-trace-base';
import { WebTracerProvider } from '@opentelemetry/sdk-trace-web';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { MeterProvider, PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-http';
import { FetchInstrumentation } from '@opentelemetry/instrumentation-fetch';
import { registerInstrumentations } from '@opentelemetry/instrumentation';
import { onCLS, onFCP, onINP, onLCP, onTTFB } from 'web-vitals';

const env = import.meta.env as Record<string, string | undefined>;

const SESSION_KEY = 'km_session_id';
const SERVICE_NAME = 'knowledge-map-web';

let started = false;

const isEnabled = (): boolean => env.VITE_OTEL_ENABLED !== 'false';

/** Идентификатор клиентской сессии: стабилен на всё время браузера. */
export function getSessionId(): string {
  if (typeof localStorage === 'undefined') {
    return '';
  }
  try {
    let sessionId = localStorage.getItem(SESSION_KEY);
    if (!sessionId) {
      sessionId = crypto.randomUUID();
      localStorage.setItem(SESSION_KEY, sessionId);
    }
    return sessionId;
  } catch {
    return '';
  }
}

function collectorBase(): string {
  const configured = env.VITE_OTEL_COLLECTOR_URL?.replace(/\/$/, '') ?? '';
  return configured;
}

export function startTelemetry(): void {
  if (started) {
    return;
  }
  if (!isEnabled()) {
    return;
  }
  started = true;

  const base = collectorBase();
  const resource = new Resource({
    [ATTR_SERVICE_NAME]: SERVICE_NAME,
    'service.namespace': 'knowledge-map',
  });

  const tracerProvider = new WebTracerProvider({ resource });
  tracerProvider.addSpanProcessor(
    new BatchSpanProcessor(new OTLPTraceExporter({ url: `${base}/v1/traces` })),
  );
  tracerProvider.register();

  const meterProvider = new MeterProvider({ resource });
  meterProvider.addMetricReader(
    new PeriodicExportingMetricReader({
      exporter: new OTLPMetricExporter({ url: `${base}/v1/metrics` }),
      exportIntervalMillis: 30_000,
    }),
  );
  metrics.setGlobalMeterProvider(meterProvider);
  const meter = metrics.getMeter(SERVICE_NAME);

  const vitalsHistogram = meter.createHistogram('km_client_web_vitals_milliseconds', {
    description: 'Web-vitals core metrics (LCP, FCP, INP, TTFB)',
    unit: 'ms',
  });
  const clsHistogram = meter.createHistogram('km_client_cls', {
    description: 'Cumulative Layout Shift',
    unit: '1',
  });
  const errorsCounter = meter.createCounter('km_client_errors_total', {
    description: 'Client-side JS errors / unhandled promise rejections',
    unit: '1',
  });

  registerInstrumentations({
    instrumentations: [
      new FetchInstrumentation(),
    ],
    tracerProvider,
    meterProvider,
  });

  window.addEventListener('error', (event) => {
    errorsCounter.add(1, {
      type: 'window:error',
      message: (event.message ?? '').slice(0, 200),
    });
  });

  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason as { message?: string } | string | undefined;
    const message = typeof reason === 'string' ? reason : (reason?.message ?? '');
    errorsCounter.add(1, {
      type: 'unhandledrejection',
      message: message.slice(0, 200),
    });
  });

  onLCP((metric) => vitalsHistogram.record(metric.value, { metric: 'LCP' }));
  onFCP((metric) => vitalsHistogram.record(metric.value, { metric: 'FCP' }));
  onINP((metric) => vitalsHistogram.record(metric.value, { metric: 'INP' }));
  onTTFB((metric) => vitalsHistogram.record(metric.value, { metric: 'TTFB' }));
  onCLS((metric) => clsHistogram.record(metric.value));
}