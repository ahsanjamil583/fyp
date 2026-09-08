# Spike 3 - Baileys and WhatsApp Desktop coexistence

Observes whether the messaging bridge and WhatsApp Desktop can stay linked to the
same account at the same time. Baileys is unofficial, so this is measured, not assumed.

- Samples: **1** every 60s
- Window: 2026-08-02T12:33:15+00:00 to 2026-08-02T12:33:15+00:00
- Healthy: **0%** of samples
- WhatsApp Desktop running in 0/1 samples

## State breakdown

| State | Samples |
|---|---|
| session_broken | 1 |

## Transitions

No state changes observed during the window.

## What this means for the plan

- **Healthy throughout**: the two sessions coexist; proceed as designed.
- **Occasional `connecting`**: normal reconnect churn, tolerable.
- **Any `session_broken` while Desktop was up**: the two are fighting for device slots.
  Mitigation is to keep messaging and voice on separate WhatsApp accounts, and to say
  so plainly in the report rather than claiming coexistence works.

## Verdict (fill in)

```text
Observation window length:                        ______
Did the Baileys session survive throughout?       ______
Did WhatsApp Desktop stay logged in?              ______
Coexistence acceptable for the demo? (yes/no)     ______
```

Raw timeline: `timeline.jsonl`