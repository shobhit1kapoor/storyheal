"""Prometheus instruments for the StoryHeal closed knowledge loop."""

from prometheus_client import Counter, Histogram


STORYBLOK_OPERATIONS = Counter(
    "storyheal_storyblok_operations_total",
    "Storyblok API attempts",
    ("operation", "result", "status_code"),
)
STORYBLOK_OPERATION_DURATION = Histogram(
    "storyheal_storyblok_operation_duration_seconds",
    "Storyblok API attempt latency",
    ("operation",),
)
WEBHOOKS = Counter(
    "storyheal_storyblok_webhooks_total",
    "Storyblok webhook processing outcomes",
    ("trigger", "result"),
)
KNOWLEDGE_RUNS = Counter(
    "storyheal_knowledge_runs_total",
    "Knowledge analysis run outcomes",
    ("result",),
)
RAG_REFRESHES = Counter(
    "storyheal_rag_refreshes_total",
    "Storyblok external-source refresh outcomes",
    ("event", "result"),
)
RAG_INDEXING_DURATION = Histogram(
    "storyheal_rag_indexing_duration_seconds",
    "Publication webhook receipt to completed RAG refresh",
)
FIRST_RESPONSE_DURATION = Histogram(
    "storyheal_first_response_duration_seconds",
    "Visitor message receipt to first AI response token",
)

