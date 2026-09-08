# Correctness and reliability

## Correctness

- Trace changed behavior through real callers and consumers.
- Compare observable behavior with explicit requirements and established contracts.
- Inspect boundary inputs, invalid inputs, state transitions, and error paths.
- Inspect supported configurations and platform-specific branches.
- Confirm changed code is reachable and connected to production paths.
- Treat tests, plans, comments, commit messages, and stored output as claims until source confirms them.
- Require an independent oracle or an unambiguous source proof. Do not accept an implementation comparing against itself.

## Reliability and lifecycle

- Trace failure, retry, timeout, cancellation, and recovery paths when applicable.
- Check resource acquisition and release across all relevant exits.
- Inspect shared state, ordering, races, deadlocks, and reentrancy when concurrency is present.
- Check partial operations, rollback behavior, and idempotency.
- Distinguish supported reachable failures from theoretical possibilities.
- Require a concrete trigger and consequence.

## Contracts and compatibility

- Identify affected public APIs, command-line behavior, configuration, schemas, protocols, generated output, and supported consumers.
- Trace implementations and known consumers across base and target.
- Check defaults, errors, ordering, serialization, and compatibility.
- Require migration handling only for established contracts.
- Do not preserve accidental internals without consumer evidence.
- Report a compatibility break only with a concrete consumer or documented contract.

## Performance

Review performance only when the change affects a performance-sensitive path or makes a performance claim.

Static evidence may establish added asymptotic work, unconditional allocation or copying, synchronization, blocking operations, repeated traversal, or destroyed locality. Label runtime magnitude unverified unless authoritative existing evidence establishes it. Never claim an optimization or regression from intuition alone.
