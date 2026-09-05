# Security maintenance

When adding a new executor, parser, network endpoint, file-backed feature, provider integration, or generated artifact path, add adversarial tests for its trust boundary and bind it to the shared hard-limit policy before exposing it through CLI, REST, or MCP.
