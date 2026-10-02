# Рабочие процессы

## Эксперимент

Опишите схему и требования → проверьте компоненты и runtime → запустите эксперимент → проверьте измерения → сохраните артефакты и отчёт. Для длительных запусков используйте durable jobs со статусом, отменой и восстановлением.

Источники: [verified workflow](../VERIFIED_WORKFLOW.md), [требования](../REQUIREMENT_ENGINEERING.md), [workspace manifests](../WORKSPACE_MANIFESTS.md), [нативные запросы](../../examples/native-project-run/README.md).

## Изображение → CircuitSpec

Изображение читает AI-хост; MCP получает JSON:

```text
изображение → CircuitSpec → validate_circuit → approve_circuit_spec
           → create_circuit → .ms14 + изображение + доказательства
```

Реестр `circuit_spec.py` включает R/C/L, DC-источники, землю, ограниченные модели диодов и BJT и идеальный операционный усилитель. Произвольные микросхемы требуют отдельной поддержки.

Нечитаемые значения и неясные соединения заносятся в `uncertainties`. Пользователь проверяет компоненты, значения и топологию перед построением. Approval привязан к конкретной спецификации; после изменения её нужно проверить заново.

`create_circuit` сохраняет CircuitSpec, SPICE, mapping компонентов, результаты проверок и manifest хешей рядом с проектом. Валидация JSON не заменяет нативную проверку в Multisim.

Источники: [JSON Schema](../circuitspec.schema.json), [примеры](../../examples/circuitspec/), [skill](../../skills/multisim-workflow/SKILL.md), [проект контракта](../circuitspec-design.md). Последний содержит исторический план; состояние реализации сверяйте с кодом и тестами.

## Исправление и оптимизация

[Инспекция](../PROJECT_INSPECTION.md) → [диагностика](../DESIGN_DIAGNOSIS.md) → [оценка patch](../DESIGN_PATCH_EVALUATION.md) → [транзакция](../DESIGN_PATCH_TRANSACTIONS.md) → повторная проверка требований.

Оптимизация: [design optimization](../DESIGN_OPTIMIZATION.md), [global optimization](../GLOBAL_OPTIMIZATION.md), [autonomous correction](../AUTONOMOUS_CORRECTION.md). Приёмки конкретных аналоговых схем перечислены в [каталоге](Documentation.md).
