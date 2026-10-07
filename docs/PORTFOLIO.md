# Presenting SignalBrief in your portfolio

## A defensible project description

Built an evidence-backed competitive intelligence application with FastAPI, CrewAI, AutoGen and Zapier. Implemented frozen source evidence, validated inter-agent contracts, durable worker leases, human review, version history, transactional notification delivery and a responsive dashboard. Verified the actual model pipeline with Groq and real public sources, and confirmed a live Zapier webhook receipt.

Avoid calling it an autonomous strategist or claiming measured business impact. The output is reviewed research and proposed experiments. Public hosting and an independently verified Slack completion are separate deployment milestones.

## What makes this addition valuable

Your existing competitor analysis, automation and agent projects already cover parts of this problem. The useful addition here is the boundary between two real agent frameworks: a verified research dossier becomes the input to a bounded critique discussion. Show the stored research-only baseline alongside the council's actions, the critic's objections, source excerpts and actual token costs. That makes the extra framework complexity open to inspection.

The engineering story includes concurrent deduplication, worker recovery, stale approval prevention and ambiguous webhook delivery. These are implemented behavior, with tests and an actual failure history, rather than architecture promises.

## Five-minute walkthrough

1. Open the completed Linear draft and its original announcement.
2. Inspect a finding beside its stored source excerpt and hash.
3. Open the actual CrewAI task outputs and all three AutoGen messages.
4. Compare the research-only actions with the final proposed experiments. Explain one unresolved assumption, such as whether a vendor setting is exposed through an API.
5. Show the review controls, version history design and durable delivery record. Explain why a Zapier HTTP 200 is different from confirmed Slack delivery.
6. Show the regression tests and one recovered failure. End with the actual deployment boundary rather than implying hosted automation is already configured.

## Interview questions

**Why both frameworks?** CrewAI provides dependent research tasks and an explicit dossier contract. AutoGen provides a bounded propose/challenge/synthesize conversation. The saved baseline lets us examine whether the second stage justifies its latency and token cost; improvement is not presumed.

**How do you handle hallucinations?** Restrict source access, preserve fetched evidence, validate schema and literal quotes, reject unknown references and require human review. Those checks do not prove entailment, so an independent reviewer still assesses claims and strategic usefulness.

**Why Zapier?** It connects existing RSS and Slack workflows while the backend owns deduplication, research state and approval authority. A stable delivery ID supports downstream duplicate suppression.

**What happens when a worker dies?** Its lease expires. Another worker resumes saved evidence/research; writes require the current ownership token. The delivery outbox survives separately and retries bounded HTTP failures.

**What would change at scale?** PostgreSQL leases, object storage, organization identities, SSO/RBAC, per-tenant credentials, process-isolated model execution, independent evaluation and downstream completion callbacks. AutoGen's maintenance status is a reason to keep its adapter isolated.
