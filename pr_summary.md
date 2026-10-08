## Summary

- Remove all \`@logger.catch\` decorators from \`a_sync.py\`, \`sync.py\`, and \`utils.py\`
- Make \`loguru\` an optional/dev-only dependency (no longer required at runtime)
- Delete legacy \`core_requirements.in/txt\` and \`dev_requirements.in/txt\`; replaced by \`uv\` dependency groups
- Update \`release.yml\` CI to use \`uv sync --group dev\` and \`uv build\`
- Bump version to **0.2.0**

## Test plan
- [ ] Pre-commit hooks pass
- [ ] \`uv sync --group dev\` resolves cleanly
- [ ] All tests pass (\`uv run pytest\`)
- [ ] Package builds (\`uv build\`)
- [ ] \`import sqlmodel_crud_utils\` works without \`loguru\` installed"
