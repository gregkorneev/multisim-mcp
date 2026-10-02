# Архитектура

```text
AI-хост → MCP server → EDA service / backend
                    → builder → XML → codec → .ms14
                    → 32-bit COM worker → Multisim
                    → raw → CSV / SVG / image / report → resources
```

CircuitSpec добавляет проверяемый контракт перед builder. Для длительных задач job engine сохраняет очередь и запускает отдельный job worker. COM принадлежит изолированному процессу.

| Путь | Назначение |
| --- | --- |
| `mcp_server/multisim_mcp/` | Сервер, CLI, контракты, backends, обработка результатов |
| `mcp_server/tests/` | Unit, протокольные и runtime-тесты |
| `docs/` | API, архитектура, ограничения, приёмки и планы |
| `examples/` | Запросы, netlists и CircuitSpec |
| `tools/` | Установка, диагностика, шаблоны и release checks |
| `skills/` | Инструкции для AI-хоста |
| `integrations/deepseek-harness/` | Интеграция DeepSeek Harness |
| `compatibility/` | Контракты совместимости |
| `.github/workflows/` | CI и публикация |
| `competition/` | Конкурсные и бизнес-материалы |

`server.py` публикует MCP API; `eda_service.py` и backends разделяют выполнение; `schematic_builder.py` строит схему; `com_worker_client.py` управляет worker; `multisim_client.py` выполняет COM-операции. `safety.py` задаёт allowlist, `experiment_resources.py` управляет артефактами.

Источники: [архитектура](../ARCHITECTURE.md), [EDA core](../EDA_CORE.md), [backends](../OPEN_EDA_BACKENDS.md), [API агента](../AGENT_API.md).
