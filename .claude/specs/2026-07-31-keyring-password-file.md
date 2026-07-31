# Мини-круг Ф-3: secret-гигиена агентской линии (`RUSTOK_KEYRING_PASSWORD_FILE`) → v0.4.2

> Статус: **ПРЕДЛОЖЕНИЕ, ждёт Гейта-1.** Кода нет до «go» Капитана.
> Триггер: аудит, находки 1.2/4.2 (пароль кошелька открытым env-var: виден в
> `podman/docker inspect Config.Env`, в истории шелла, в MCP-JSON на диске).
> Консольная линия закрыла это в PR-1.1 (`e0b7a1f`); на агентскую не переносилось.
> База: `release/wallet-v0.4.x` (после #93). Эталон: `e0b7a1f` (доказан двумя
> раундами Гейта-2 + live e2e на podman).

## Цель

Пароль кейринга можно передать **файлом** (стандартная `_FILE`-конвенция):
`podman secret …,type=mount` на podman, bind-mount 0600-файла на docker —
plaintext исчезает из `inspect`, MCP-конфигов и истории шелла. Явный
`RUSTOK_KEYRING_PASSWORD` продолжает работать (обратная совместимость для
текущих установок). Все публичные каналы учат только этому способу.

## Скоуп — входит

1. **PR-D1 в `release/wallet-v0.4.x`** (`feat/keyring-password-file`):
   - `scripts/rustok-wallet-entrypoint.sh`: дословный порт блока из `e0b7a1f`
     (~20 строк: `_FILE` если env не задан; env всегда выигрывает; `$(cat …)`
     стрипит хвостовые newline; именованные ошибки на не-файл/нечитаемый
     (FIFO/device/dir/SELinux) и пустой файл — ДО старта core, не 60-с вис).
     Префикс сообщений — `rustok-wallet:` (агентский), не tui.
   - **Тесты — новый e2e-модуль `tests/e2e/test_password_file_e2e.py`** (podman,
     маркер, skip без podman; red→green против образа): unlock через
     `podman secret …,type=mount` с паролем с кавычками/`$` (байт-точно);
     **строгий ассерт отсутствия пароля в `podman inspect`** (raw +
     json-escaped формы, позитивный контроль против вакуума); precedence
     (`-e` выигрывает); негативы: нет файла / пустой / директория —
     именованные ошибки; обратная совместимость `-e`. Красная фаза — прогон
     против образа v0.4.1 (там `_FILE` игнорируется). Docker bind-mount —
     **manually probed only** (docker на машине нет; тот же ratified-паттерн,
     что у консольной), параметризация доставки пароля в тестах закладывается.
   - Доки агентской линии на `_FILE`/secret (обе движковые ветки, как у
     консольной): `docs/INSTALL.md`, `docs/TROUBLESHOOTING.md` (+ новый пункт:
     «30-с таймаут handshake → вы на ≤0.4.0, обновитесь до ≥0.4.1»),
     `docs/CONFIGURATION.md` (строка `_FILE` в таблице env), `smithery.yaml`
     (configSchema → файл, не открытое поле пароля), `skills/rustok-wallet/SKILL.md`
     (секция пароля: env-file 0600 → `podman secret`/bind-mount `_FILE`;
     версия 0.4.6), `skills/rustok-wallet/claw.json` (0.4.6).
   - Манифесты: `server.json` → 0.4.2, `CHANGELOG.md` [0.4.2].
2. **PR-D2 в `rustok-landing`** (соседний репо): rung-1 `Install.astro` —
   те же `_FILE`-инструкции + podman-строка (по образцу SKILL.md 0.4.5+).
3. **Живая приёмка** (после merge, на собранном образе v0.4.2):
   e2e-модуль зелёный + `podman secret` путь + `claude mcp list → connected`
   с `_FILE`-доставкой (регрессия handshake после Ф-1).
4. **Паблиш-поезд (по «добру»):** тег `wallet-v0.4.2` → образ `v0.4.2` +
   floating `v0.4`/`v0` + `latest` (та же ратификация, что для v0.4.1) →
   Registry re-publish 0.4.2 (могу сам, `mcp-publisher` на машине) → ClawHub
   0.4.6 (Капитан, веб-UI) + тег `skill-v0.4.6` → живые приёмки каналов.

## Скоуп — ЯВНО не входит

- Полная движко-нейтральность/шим `rustok` (Ф-4), deprecate temrjan-записи
  реестра (Ф-5), `docs/CONFIGURATION.md` правка txguard-фразы (Ф-6),
  телеметрия (Ф-7), донат в `instructions` (Ф-8).
- Код `src/` (python) — не трогаем вообще: `_FILE` читает entrypoint, до core.
- approve-консоль/approval-гейт (ADR).

## Затронутые файлы

PR-D1: `scripts/rustok-wallet-entrypoint.sh`, `tests/e2e/` (новые),
`docs/{INSTALL,TROUBLESHOOTING,CONFIGURATION}.md`, `smithery.yaml`,
`skills/rustok-wallet/{SKILL.md,claw.json}`, `server.json`, `CHANGELOG.md`.
PR-D2: `rustok-landing/src/components/Install.astro` (только rung-1 блоки).

## Решения (предрешены)

1. **Дословный порт `e0b7a1f`** — блок прошёл два раунда Гейта-2 и live e2e;
   меняется только префикс сообщений.
2. **Обратная совместимость `-e` сохраняется** (900 установок не ломаем) —
   env явно задан → файл даже не читается (как в эталоне).
3. **Версия образа 0.4.2 (patch)**: фича обратно-совместимая, линия
   maintenance; конвенция линии (0.4.1) сохраняется.
4. **Доки — обе движковые ветки** (podman secret / docker bind-mount), без
   шима: полная нейтральность — Ф-4.
5. **e2e-модуль — первый на агентской линии**: заодно начинает закрывать
   находку 8.3 (всеядная приёмка) — маркер `e2e`, не блокирует unit-CI
   (skip без podman).

## Критерии приёмки

1. True-red: новый e2e против образа v0.4.1 — падает на `_FILE`-сценариях
   (фиксация вывода); green — против v0.4.2-rc.
2. Строгий ассерт: пароль (raw и escaped) отсутствует в `podman inspect`
   при обеих доставках на podman; позитивный контроль (ассерт не вакуумный).
3. Именованные ошибки на 3 негативах (verbatim), без 60-с виса.
4. `claude mcp list → connected` с `_FILE`-доставкой (регрессия Ф-1 не сломана).
5. Греп-инварианты доков: 0 plaintext-образцов пароля в
   SKILL.md/INSTALL/TROUBLESHOOTING/smithery/лендинге.
6. Каналы после поезда: Registry 0.4.2 isLatest, ClawHub 0.4.6 live.

## Definition of Done

PR-D1 + PR-D2 смержены · тег `wallet-v0.4.2` · образ под v0.4.2/v0.4/v0/latest ·
Registry 0.4.2 · ClawHub 0.4.6 (+`skill-v0.4.6`) · живые приёмки зелёные ·
бэклог: Ф-3 closed (1.2/4.2 закрыты во всех каналах) · отчёт в `.claude/reports/`.

## Тест-план

- red: e2e против v0.4.1-образа (ожидаемые падения — в отчёт).
- green: e2e против свежего образа + unit-сюита (184) + ruff/format/mypy/
  shellcheck.
- live: podman secret → create-wallet → unlock → inspect-ассерт;
  `claude mcp list` с `_FILE`; docker-ветка — ручная проба задокументирована
  (среды нет), в тестах помечена honestly.
- regression: handshake-проба из Ф-1 (echo + wire-форма) на новом образе.
