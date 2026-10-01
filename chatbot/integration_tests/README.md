These tests target the sibling ShopNest integration, so run them separately from
Master Chatbot tests to avoid the two projects' `app` package names colliding:

```bash
PYTHONPATH=/absolute/path/to/ShopNest/backend DATABASE_URL=sqlite:// \
  python3 -m pytest -q chatbot/integration_tests/test_shopnest.py
```

The tests mock persistence and do not access customer records or production databases.
