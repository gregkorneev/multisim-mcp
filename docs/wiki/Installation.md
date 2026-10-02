# Установка

Для нативного запуска нужны Windows 10/11, лицензированный NI Multisim 14+, Python для MCP и 32-битный Python для COM worker. Frontend может быть 32- или 64-битным. Кодек `.ms14` использует Node.js.

Из корня репозитория запустите:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/install-windows.ps1
```

Установщик готовит окружение, кодек, локальные шаблоны и фрагмент настроек Codex в `%LOCALAPPDATA%/MultisimMcp`. Конфигурацию клиента необходимо обновить по инструкции. Перед созданием шаблонов сохраните открытые проекты Multisim. Не перемещайте editable checkout без переустановки.

Параметры: `-SkipTemplates`, `-Python32`, `-SamplesRoot`, `-SelfCheck`. Полное описание: [установка на русском](../INSTALL_WINDOWS_RU.md).

```powershell
multisim-mcp --help
multisim-mcp --json doctor
```

В MCP вызовите `runtime_status`. Проверьте COM, лицензию, worker, кодек и component pack отдельно: успешная инспекция ещё не означает готовность нативной симуляции.

Источники: [разные клиенты](../MULTI_CLIENT_INSTALL.md), [README сервера](../../mcp_server/README.md), [совместимость](../COMPATIBILITY.md), [локальные шаблоны](../NATIVE_COMPONENT_INTEGRATION_GUIDE.md).
