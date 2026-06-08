# How to Debug Microservices — Research Synthesis

## Core challenges of debugging microservices
- No single stack trace — a single user request may traverse 10+ services
- Logs are scattered across many services, hosts, and containers
- Asynchronous messaging (Kafka, RabbitMQ, SQS) breaks the request/response mental model
- Network failures, latency spikes, partial degradation
- Cascading failures (one slow service takes down its neighbors)
- State is distributed; reproducing a bug locally is hard
- Traditional `breakpoint` debuggers don't work in production

## The three pillars of observability
1. **Logs** — discrete events (what happened)
2. **Metrics** — aggregated numerical data (how much, how often)
3. **Traces** — causal request flow across services (where did time go)

A mature debugging workflow uses all three.

## Centralized logging
- **ELK Stack** (Elasticsearch + Logstash + Kibana) — the most widely adopted; powerful search, mature ecosystem
- **EFK Stack** (Elasticsearch + Fluentd + Kibana) — Fluentd is lighter than Logstash, popular in Kubernetes
- **Grafana Loki + Promtail** — cost-efficient, indexes labels instead of full text; pairs naturally with Grafana
- **Splunk, Datadog, Graylog** — commercial/SaaS options with rich features
- All require **structured (JSON) logging** with consistent fields: `timestamp`, `level`, `service`, `traceId`, `spanId`, `correlationId`, `message`, `context`

## Distributed tracing
- **OpenTelemetry** — vendor-neutral standard for instrumentation (traces + metrics + logs); the de-facto choice in 2024+
- **Jaeger** — CNCF-graduated, built at Uber, designed for high scalability, often the default OpenTelemetry backend
- **Zipkin** — older, originally from Twitter, simpler, lighter footprint
- **Tempo, Datadog APM, New Relic, Honeycomb** — alternatives/backends
- Tracing answers: "which service is slow?", "where did this error originate?", "what's the dependency graph of a request?"

## Metrics & monitoring
- **Prometheus** — pull-based metrics scraping, CNCF standard, ~75% adoption in cloud-native
- **Grafana** — dashboards and visualization, can query Prometheus + Loki + many other sources
- **Alertmanager** — alerting on metrics
- RED method (Rate, Errors, Duration) for services; USE method (Utilization, Saturation, Errors) for resources

## Correlation IDs (the glue)
- A unique ID generated at the edge (API gateway or first service) per incoming request
- Propagated via HTTP headers (e.g. `X-Correlation-Id`, W3C `traceparent`) and message-baggage
- Logged with every log line in every service
- Lets you pivot from "one bad log" to "all logs for this request" instantly
- This is the single most impactful pattern for cutting debug time

## Local development debugging
- Run services as local processes when possible (Node.js, Go, Python all make this easy)
- Use **docker-compose** to spin up dependencies (DBs, brokers) while running your service natively
- **Hot-reload / devtools** — Spring Boot DevTools, Nodemon, Air (Go), etc.
- **Attach remote debuggers** to containers in staging via JDWP (JVM) or `dlv` (Go) over a debug port
- **Telepresence / mirrord / Gefyra** — run your service locally while it joins the remote cluster's network, so it can talk to real services in the cluster
- **Service mocking** — WireMock, Mountebank, Hoverfly for stubbing downstream services

## Service mesh debugging (Istio, Linkerd)
- Mesh sidecars capture **L7 traffic metrics** automatically (request rate, latency, error rate per route)
- **Distributed tracing headers are propagated** by Envoy sidecars — no app changes needed
- **`istioctl analyze`** — checks config for issues
- **Kiali** — visualizes the service graph and traffic flows
- **Envoy access logs** — detailed per-request logs from the sidecar
- **Traffic mirroring / shadowing** — duplicate live traffic to a debug instance of a service to reproduce bugs in production-like conditions without user impact. AWS VPC Traffic Mirroring is the cloud-level equivalent.

## Health checks & introspection
- Kubernetes liveness/readiness/startup probes
- Spring Boot Actuator: `/actuator/health`, `/actuator/beans`, `/actuator/env`, `/actuator/metrics`
- gRPC health checking protocol
- Custom readiness signals (warmup done, caches primed)

## Production debugging techniques
- **Structured logging** with context propagation
- **Sampling traces** (100% in dev, lower % in prod for cost)
- **Feature flags** to enable verbose logging per-user/per-request
- **Traffic mirroring** for safe repro of production bugs
- **Chaos engineering** (Chaos Mesh, Litmus) to surface weaknesses
- **Profiling** in prod via continuous profilers (Pyroscope, Parca, Datadog Continuous Profiler)
- **Debug binaries** — keep symbols, use `dlv attach` (Go), `jstack`/`async-profiler` (JVM)

## Best practices checklist
- [ ] Structured JSON logs in every service
- [ ] Correlation ID generated at the edge and propagated everywhere
- [ ] OpenTelemetry instrumentation in every service
- [ ] Centralized log aggregation (Loki/ELK)
- [ ] Prometheus metrics + Grafana dashboards
- [ ] Distributed tracing backend (Jaeger/Tempo)
- [ ] Health endpoints + Kubernetes probes
- [ ] Alerts on SLOs, not just infrastructure
- [ ] Runbooks for common failure modes
- [ ] Local-dev tooling (docker-compose, telepresence)
- [ ] Staging environment that mirrors production
- [ ] Traffic mirroring capability for safe repro

## Common anti-patterns to avoid
- Logging only errors (you lose context for intermittent bugs)
- Using different correlation-ID header names per service
- Inconsistent timestamp formats across services
- Storing logs only on local disk (lost when pods are rescheduled)
- Debugging only locally with mocked services that drift from prod
- Not instrumenting message-queue consumers (forgotten half of the trace)
