# Разработка и проверки

Python 3.10+; зависимости заданы в `mcp_server/pyproject.toml`.

```sh
python -m venv .venv
# POSIX: source .venv/bin/activate
# Windows: .venv/Scripts/Activate.ps1
python -m pip install -e ./mcp_server
python -m unittest discover -s mcp_server/tests -t mcp_server
python -m pip install build
python -m build mcp_server
```

COM-free тесты проверяют контракты, валидацию и orchestration. Runtime-тесты могут пропускаться без Multisim/ngspice. Нативные изменения проверяются отдельно на Windows с версией Multisim и сохранёнными доказательствами.

[CI](../../.github/workflows/ci.yml) содержит Windows-проверки, 32-битный протокол, Linux introspection и ngspice.

Вики хранится в `docs/wiki`. Обновляйте тематические страницы вместе с кодом и добавляйте новые документы в [каталог](Documentation.md). Подробные контракты остаются в основных документах.

Рабочий fork: `gregkorneev/multisim-mcp` (`origin`); исходный проект: `yxy050208/multisim-mcp` (`upstream`). Push в fork не публикует пакет или release.

Источники: [CONTRIBUTING](../../CONTRIBUTING.md), [release checklist](../RELEASE_CHECKLIST.md), [publishing](../PUBLISHING.md), [upstream audit](../upstream-audit.md).

## Проверка снимка — 2 октября 2026

Проверено на macOS в отдельном Python-окружении:

- Все локальные ссылки вики разрешаются.
- Wheel и sdist версии `1.3.0rc1` успешно собраны.
- Unit suite: 831 тест, 18 failures, 6 errors, 47 skipped. Прогон не прошёл.
- Есть несовместимые с macOS ожидания Windows-путей в CLI и handoff-тестах.
- CircuitSpec regression test ожидает два JSON-примера, в исходниках присутствуют три.
- DeepSeek compatibility и plugin release checks не прошли: контракт ожидает core/experiment/optimization/full = 29/84/70/107, код возвращает 31/87/70/110.
- Текстовый whitespace check проходит с учётом CRLF; PDF исключён из проверки текстовых пробелов.

Нативные Windows/COM операции в этом прогоне не проверялись. Push этого снимка не означает успешный CI или готовность release.
