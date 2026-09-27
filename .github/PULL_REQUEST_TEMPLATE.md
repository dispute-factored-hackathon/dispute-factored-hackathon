## Summary

<!-- What changed and why? -->

## Linked issue

Closes #<!-- issue number -->

## Scope and user stories

- User stories:
- Requirements:
- Mocked components or limitations:

## Validation

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run coverage run --source=dispute_agent -m unittest discover -s tests -v`
- [ ] `uv run coverage report --fail-under=75`
- [ ] `uv run radon cc dispute_agent -s -a`
- [ ] Positive, negative, uncertainty, abuse and handoff paths considered where relevant

## Quality metrics

| Metric | Before | After |
|---|---:|---:|
| Tests passing | | |
| Statement coverage | | |
| Average cyclomatic complexity | | |
| Highest function complexity | | |
| Maintainability index | | |

## Safety and data review

- [ ] Uses only synthetic or explicitly authorized test data
- [ ] Does not expose credentials or unmasked sensitive values
- [ ] Does not describe mock identification or external actions as production behavior
- [ ] Consequential state changes remain deterministic or require human approval
- [ ] Traces and logs contain no real customer data

## Reviewer notes

<!-- Trade-offs, migration notes, screenshots, traces, or areas needing special attention. -->
