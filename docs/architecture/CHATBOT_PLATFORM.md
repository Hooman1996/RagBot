# Knowledge and prompt selection

The former platform mode and session binding design is superseded by the
[knowledge selection correction](KNOWLEDGE_SELECTION_CORRECTION_REPORT.md).

Documents are selected on each request. A conversation can switch between
General_FAQ, NegahBoom_FAQ and other available sources without changing its
session or history. Prompt selection follows the current validated selection;
it does not control ownership or retrieval access.

`CHATBOT_PLATFORM` and `X-Chatbot-Platform` are obsolete and ignored. Old stored
platform fields are unused and require no migration. Production deployments
continue to have separate storage through their ordinary configuration.
No re-ingestion is required.
