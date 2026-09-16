# Provider options shown during setup

The setup wizard must describe provider support from `metis_head.provider_capabilities`, not infer support from a credential, a running process, or a UI label. The capability response contains no credentials and is safe to return from a setup API.

## Current choices

| Choice | Selectable now | Why |
| --- | --- | --- |
| Ollama (local) | Yes | Metis has an Ollama chat adapter. Setup still needs a model, and runtime probing must verify that Ollama is reachable and the model is installed. |
| OpenAI API (usage-based) | No | The current Metis provider explicitly refuses OpenAI dispatch. A key by itself is not implementation. Future availability requires implemented dispatch, explicit enablement, a key, and a model. |
| Codex App Server (ChatGPT sign-in) | No | OpenAI documents ChatGPT-managed authentication and the App Server protocol, but Metis has neither integrated that protocol as a model provider nor supplied a least-authority guard for Codex agent capabilities. |

Disabled choices remain visible so setup tells the truth about why they cannot be selected. The UI must render `selectable` and `status` as returned; it must not turn an unavailable choice on based on browser state or local storage.

## Billing and authentication boundary

An ordinary OpenAI API key uses usage-based API billing. A ChatGPT subscription is not a pool of ordinary API credits. Codex can separately use ChatGPT sign-in for subscription access, subject to the account's plan limits, but that does not make the ordinary OpenAI API path subscription-funded.

Metis setup does not display, persist, or return API keys or Codex tokens. The capability contract only checks whether required configuration is present. Secret handling belongs to the existing secret/configuration boundary, not to setup state.

## Availability gates

The default capability call is fail-closed. Ollama is selectable; OpenAI API and Codex App Server are unavailable. Future integration code must explicitly affirm all applicable gates:

- OpenAI API: dispatch is implemented, `METIS_ENABLE_OPENAI_API` is true, and both API key and model are configured.
- Codex App Server: the provider integration and a least-authority guard are both implemented.

These flags are integration assertions, not end-user switches. They prevent a partially completed feature from appearing available.

## Official sources

- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)
- [Codex authentication](https://developers.openai.com/codex/auth/)
- [Codex App Server](https://developers.openai.com/codex/app-server/)
- [Ollama API documentation](https://github.com/ollama/ollama/blob/main/docs/api.md)
