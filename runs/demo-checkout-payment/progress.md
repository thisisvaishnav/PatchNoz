# Incident Run: `demo-checkout-payment`

## Timeline
- **Alert received**: `Checkout latency spike` (severity: `critical`, service: `checkout`)
- **Evidence collected**: 4 item(s) from SigNoz
  - `[METRICS]` checkout metrics: p99 latency 6014.83ms, error rate 7.77%
  - `[TRACES]` Slowest recent trace on 'checkout': HTTP POST (136.06ms)
  - `[TRACES]` Slowest recent trace on 'payment': grpc.oteldemo.PaymentService/Charge (10.76ms)
  - `[LOGS]` 10 recent log entries for 'payment'; latest: Transaction complete.
- **Root cause diagnosed**: `payment` (confidence: 85%)
  - Checkout latency appears to be dominated by payment charge spans. The likely root cause is slow or failing payment processing during checkout.
  - **Recommended fix**: Add timeout, retry, and circuit-breaker handling around the payment charge call. Add metrics for payment dependency latency and error rate.
- **Action `slack`**: dry_run
- **Action `github`**: dry_run
