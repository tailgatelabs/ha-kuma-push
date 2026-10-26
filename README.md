# Uptime Kuma Push for Home Assistant

Sends a heartbeat from Home Assistant to an [Uptime Kuma](https://github.com/louislam/uptime-kuma)
**Push** monitor on a fixed interval. If Home Assistant (or its network) goes down, the
heartbeats stop and Uptime Kuma alerts you.

- One HTTP GET per interval, nothing else. No polling of Uptime Kuma, no dependencies.
- Reports the round-trip time of the previous push as Uptime Kuma's `ping`.
- Configuration: push URL and interval. That's it.

## Installation (HACS custom repository)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/tailgatelabs/ha-kuma-push`, type **Integration**.
2. Install **Uptime Kuma Push**, restart Home Assistant.
3. **Settings → Devices & services → Add integration → Uptime Kuma Push**.

Manual alternative: copy `custom_components/kuma_push` into your `config/custom_components/`.

## Setup

1. In Uptime Kuma, create a monitor of type **Push**. Set its *Heartbeat Interval* to at least
   the push interval you'll use in Home Assistant (add some slack, e.g. 90 s for a 60 s push).
2. Copy the push URL (e.g. `https://kuma.example.com/api/push/abc123?status=up&msg=OK&ping=`).
   The query string is ignored; the integration sends its own.
3. Paste it into the config flow and pick an interval (20–86400 s, default 60). A test push is
   sent before the entry is created.

The interval can be changed later via **Configure**. Add the integration once per push monitor.

## Entities

| Entity | Type | Description |
| --- | --- | --- |
| `binary_sensor.<host>_push_status` | `problem` | `on` when the last push failed. Attribute `last_error` holds the reason. |
| `sensor.<host>_next_push` | `timestamp` | When the next push is scheduled. |
| `sensor.<host>_last_successful_push` | `timestamp` | Time of the last accepted push. |

Entities stay available while pushes fail, so the failure is visible as state rather than
`unavailable`. A failure is logged once at warning level; recovery is logged once at info level.
Pushing continues even if all entities are disabled.

### Countdown on a dashboard

Timestamp sensors are rendered by the frontend as a live relative time ("in 42 seconds"),
so a countdown needs no extra state updates:

```yaml
type: entities
entities:
  - entity: binary_sensor.kuma_example_com_push_status
  - entity: sensor.kuma_example_com_next_push
  - entity: sensor.kuma_example_com_last_successful_push
```

`tile` cards work as well.

### Alerting on failure

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.kuma_example_com_push_status
    to: "on"
    for: "00:05:00"
actions:
  - action: notify.notify
    data:
      message: "Uptime Kuma push failing: {{ state_attr(trigger.entity_id, 'last_error') }}"
```

### Recorder

`next_push` changes on every push. To keep it out of the database:

```yaml
recorder:
  exclude:
    entities:
      - sensor.kuma_example_com_next_push
```

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
ruff check . && ruff format --check .
pytest   # enforces 100% coverage
```
