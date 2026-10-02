# Диагностика и ограничения

| Симптом | Что проверить |
| --- | --- |
| Сервер отвечает, Multisim не запускается | Windows, лицензия, COM registration, 32-битный worker |
| Неверный Python worker | `MULTISIM_MCP_WORKER_PYTHON` и разрядность |
| Нет шаблона компонента | Локальный component pack, manifest, модель |
| CircuitSpec отклонён | Тип, значение, terminals, nets, uncertainties, approval |
| Выходные файлы существуют | Новый путь либо осознанный `overwrite` |
| Job прерван | Сохранённое состояние, lease, журнал и recovery |
| SPICE-модель не поддерживается | Совместимость и происхождение модели |

Начните с CLI `doctor` и MCP `runtime_status`. Для воспроизведения сохраните запрос, версии пакета, ОС, Multisim, Python worker и очищенный журнал.

Источники: [recovery](../RECOVERY.md), [runtime validation](../REAL_RUNTIME_VALIDATION.md), [security](../../SECURITY.md), [coverage](../COMPONENT_COVERAGE.md), [SPICE provenance](../SPICE_COMPATIBILITY_AND_PROVENANCE.md).

Приёмка подтверждает конкретную схему и версию, указанные в документе. Она не доказывает поддержку любого устройства или готовность физического изделия. NI XML, vendor models, приватные схемы, ключи и runtime-артефакты не включаются в публичную поставку.
