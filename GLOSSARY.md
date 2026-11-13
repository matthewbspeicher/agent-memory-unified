# Agent execution

Newly resolved execution terms. Established project vocabulary remains in
[CONTEXT.md](CONTEXT.md).

## Language

**Order outcome**:
The known execution facts about an order attempt: dispatch evidence, uncertainty,
and any measured fill progress. It is distinct from an Opportunity's lifecycle
status and does not, by itself, establish permission to retry.
_Avoid_: Opportunity status, execution success

**Opportunity offer**:
A saved Opportunity presented for human approval, identified by its saved
revision and the time it was offered. Capturing an offer does not claim it,
approve it, or guarantee that it remains current.
_Avoid_: Approval, execution permission
