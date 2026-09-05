# Security CI contract

Security-sensitive behavior must remain testable from both source and the exact built wheel. A refactor that weakens or removes a trust gate, hard resource ceiling, path confinement rule, parser restriction, integrity check, remote-auth requirement, or release-preflight check must fail CI until the replacement provides equivalent or stronger protection.
