# worker (Async Job Queue Worker)

**Purpose**: Processes asynchronous jobs from NATS message broker.

**Structure**:
```
src/
  main.rs      # NATS subscriber loop, job handling
```

**Functionality**:
- Connects to NATS server
- Subscribes to job subjects (e.g., `worker.hello`)
- Deserializes incoming MessagePack-encoded jobs
- Processes jobs and sends replies
- Example: HelloRequest -> HelloResponse

**Job Queue Pattern**:
- Uses async-nats with request-reply pattern
- Jobs defined in `yappr-shared::jobs` as trait impls
- Type-safe: subject and response type encoded in trait
- Serialization: MessagePack (rmp-serde) for performance
