# Этап 5 — MCP-тулы execute_transaction / get_execution_status (tui-линия)

> Управляющий источник: core `specs/2026-07-05-slice1b-tui-approver.md` §Этап 5, с поправками
> пост-ренейма (ADR core `decisions/2026-07-10-two-products-naming.md`): контейнер =
> `rustok-wallet-tui`. Разведка контракта — core `crates/gateway/src/lib.rs` (роуты 96–110,
> хендлеры 369–460, структуры 695–719) — POST execute-роут СУЩЕСТВУЕТ, мини-PR в core не нужен.

## Цель

Дать агенту консольной линии (wallet-tui) возможность отправить одобренную человеком транзакцию
в парковку и следить за её судьбой: `execute_transaction` паркует превью в PendingStore
(fail-closed, ядро с #86 НЕ исполняет без человека), `get_execution_status` поллит исход.
Человек решает в отдельном окне (`docker exec -it rustok-wallet-tui rustok-console`);
MCP-слой к сокету одобрения не прикасается.

## Контракт core gateway (снят с кода, не с доков)

- `POST /api/v1/wallet/execute_transaction`, тело `{preview_id: string, approval?: string}`.
  `approval` — DEPRECATED `0x`-hex; в проде валидный токен невыдаваем, пусто/absent → пустые
  байты, запрос паркуется в любом случае. Ответ = execution_json.
- `GET /api/v1/wallet/execution_status?preview_id=<uuid>`. Ответ = execution_json.
- execution_json: `{state, tx_hash, error_reason, not_after_unix}`; пустые строки и нулевой
  дедлайн сериализуются как `null`. `state` ∈ `pending | executed | denied | expired | failed`
  (+ `unknown` для out-of-range enum — терминальным не считать).
- `not_after_unix` — абсолютный unix-дедлайн (секунды); после него pending истекает → `expired`.
- Ошибки: unknown/протухший `preview_id` → gRPC NotFound → HTTP 404 `{"error":"not_found",
  "message":…}`; кривой `approval`-hex → 400; ядро недоступно → 503 `core_unavailable`.

## Скоуп PR

### Входит

1. **`gateway.py`** — два метода клиента:
   - `execute_transaction(preview_id: str)` → POST `/api/v1/wallet/execute_transaction`
     с телом `{"preview_id": preview_id}`. Поле `approval` НЕ отправляем (Р-A ниже).
   - `get_execution_status(preview_id: str)` → GET `/api/v1/wallet/execution_status`,
     `params={"preview_id": preview_id}`.
2. **`protocol.py` + `gateway.py`** — маппинг `not_found`: новый код `ERR_NOT_FOUND = -32014`,
   кейс `"not_found"` в `_error_from_response` → `McpError(ERR_NOT_FOUND, message)` (Р-B).
   Без него агент на протухшем id получает замаскированный «Gateway internal error»
   и не понимает, что поллить больше нечего.
3. **`handlers.py`** — две фабрики + регистрация тулов (паттерн существующих):
   - `execute_transaction` — args `{preview_id: string}` (required). Stub-fallback (client=None):
     `{"state": "pending", "tx_hash": None, "error_reason": None, "not_after_unix": None}`.
   - `get_execution_status` — args `{preview_id: string}` (required). Stub-fallback: тот же формат.
   - Stub-fallback `next_step` НЕ получает (НИТ ревью Гейта-1, решение Инженера): обогащение —
     только на пути реального клиента; заглушка не должна отправлять человека в консоль ради
     несуществующей транзакции.
   - Обогащение по прецеденту `_with_balance_eth` (с обязательным isinstance-guard: не-dict
     ответ возвращается как есть): если в ответе `state == "pending"` — добавить поле
     `next_step` с текстом для человека (Р-C): открыть отдельный терминал и выполнить
     `docker exec -it rustok-wallet-tui rustok-console` (НОВОЕ имя контейнера — спека §Этап 5
     написана до ренейма 2026-07-10).
   - Обновить `SERVER_INSTRUCTIONS` (handlers.py:15–30): 1–2 предложения — execute паркует
     транзакцию (сервер не исполняет), человек одобряет в console-окне; текст писался до
     console-flow и этого не знает.
   - Тексты description (этикет, не защита — §3 core-спеки): агент показывает человеку
     карточку-резюме превью (кому/что/сумма/риск) ДО execute; сам `docker exec` НЕ выполняет
     и не предлагает выполнить за человека; PIN в чат не просить; статус поллить разумно —
     по запросу человека или раз в ~15–30 с до `not_after_unix` (если дедлайн `null` —
     только по запросу человека), стоп на терминальном статусе
     (`executed`/`denied`/`expired`/`failed`); `denied` = ответ человека «нет», уважать, не
     пере-парковывать тот же preview_id.
4. **`capabilities.py`** — `CAPABILITY_MAP` += `execute_transaction` / `get_execution_status`
   → `Capability.EXECUTE_TX`.
5. **Доки:**
   - `skills/rustok-wallet-tui/SKILL.md` — таблица Tools +2 строки; behavioral guidelines —
     полный approve-flow (preview → показать карточку → execute → PENDING → человек в окне
     консоли → поллить статус → терминальный исход), пункт про `denied`/`expired`.
   - `docs/CONFIGURATION.md` — строка `execute_tx` в таблице капабилити: перечислить новые тулы.
   - `CHANGELOG.md` — запись `[0.6.0]` по Keep a Changelog: Added (два тула, `not_found`-маппинг,
     LABEL source), Changed (версия/теги 0.6.0) (МИНОР-2 ревью Гейта-1).
6. **Версия 0.5.0 → 0.6.0** (Р-D) — полный реестр пинов (снят грепом по репо, /check):
   - 7 version-полей: `pyproject.toml:3`, `server.json:5`, `skills/rustok-wallet-tui/claw.json:3`,
     `skills/rustok-wallet-tui/SKILL.md:4` (frontmatter), `src/rustok_mcp/__init__.py:3`,
     `main.py:52`, `handlers.py:94` (serverInfo);
   - 8 image-тегов `…rustok-wallet-tui:v0.5.0 → v0.6.0`: `server.json:14` (OCI identifier),
     `SKILL.md:52,81,113`, `docs/INSTALL.md:16,32,53`, `docs/TROUBLESHOOTING.md:10`;
   - 3 коммент-примера в `Dockerfile.wallet:11,13,16` — локальный тег `rustok-wallet-tui:0.5.0`
     (без `v`) → `0.6.0` (МИНОР-1 ревью Гейта-1);
   - 4 пина в yaml/sh (найдены fleet-ревью: греп реестра не покрывал эти расширения):
     `smithery.yaml:10,34`, `scripts/install.sh:7`,
     `skills/rustok-wallet-tui/scripts/health-check.sh:8`.
   Гард `test_claw_manifest_version_matches_pyproject` держит синк claw↔pyproject;
   `wallet-publish.yml` версию не хардкодит (dispatch-input сверяется с pyproject).
   ⚠️ Следствие для ops: доки/манифесты после мержа указывают на ещё не собранный образ
   v0.6.0 (прецедент Этапа 4) — registry/ClawHub-ops только ПОСЛЕ сборки+пуша образа.
7. **`Dockerfile.wallet`** — добавить `LABEL org.opencontainers.image.source=
   "https://github.com/rustok-org/mcp"` (ратифицированный хвост хэндоффа 2026-07-11:
   без него GHCR не автолинкует пакет к репо).
8. **Тесты (red→green):** см. тест-план.

### ЯВНО не входит

- Правки core / console — роут есть, контракт снят с кода.
- E2E против собранного образа, pty-приёмка, podman-tmpfs — Этап 6.
- Сборка/публикация образа 0.6.0, ClawHub/MCP-Registry листинги — релизные ops (Капитан).
- Elicitation, Telegram-push, демон-режим, host-native console — вне скоупа арки (§8 core-спеки).
- Агентская линия (0.4.x, `execute_send`) — НЕ трогать ни байтом.
- `sign_typed_data`-тул (роут в gateway есть, но тула нет и §Этап 5 его не просит) —
  «замечено, не трогаю».

## Решения, вынесенные на ратификацию Гейта-1

- **Р-A. `approval`-параметр в схему тула НЕ выносим.** Рекомендация: скрыть. Почему: поле
  deprecated, в проде валидный токен невыдаваем — параметр только приглашает агента слать мусор.
  Контраргумент: потеря dev-хука для тестовых сборок ядра; не перевесил — MCP-тесты мокают
  транспорт, живому ядру поле не нужно. Цена ошибки: минорная, добавить параметр позже —
  обратимо. Изменил бы выбор: появление легитимного эмитента токенов.
- **Р-B. `not_found` → новый `ERR_NOT_FOUND = -32014`** (продолжение серии -3201x), не
  переиспользование `ERR_INVALID_PARAMS`. Почему: «id неизвестен/протух» — runtime-исход
  поллинга, агенту нужен машинный признак «прекратить поллинг», а -32602 семантически «кривые
  аргументы вызова». Цена ошибки: минорная (перенумеровать код до релиза). Изменил бы выбор:
  указание Капитана держать сетку кодов замороженной.
- **Р-C. Обогащение PENDING-ответа полем `next_step`** (строка для человека с командой консоли)
  поверх инструкции в description. Почему: description агент может не перечитать в момент
  результата; поле в ответе — в контексте ровно тогда, когда нужно. Контраргумент: дублирование
  текста; не перевесил — это один короткий стринг. Цена ошибки: косметика.
- **Р-D. Версия = 0.6.0** (не 0.5.1). Почему: новые тулы = фича → semver minor; 0.5.0 уже
  отгружен образом 2026-07-10 без этих тулов (исходная спека писалась, когда 0.5.0 ещё не
  уехал). Контраргумент: «0.5.x = консольная линия» читается как пин на 0.5; не перевесил —
  линия определена как «0.5.x+» (ADR two-products). Цена ошибки: перенумеровать до тега —
  дёшево. Изменил бы выбор: решение Капитана вести линию патчами.
- **Р-E. Image-теги в доках/манифестах бампим на v0.6.0 в этом же PR.** Почему: скилл/доки
  0.6.0, указывающие на образ v0.5.0 без execute-тулов, онбордят юзера на кошелёк, где фича
  релиза не работает. Контраргумент: окно «доки указывают на несуществующий образ» до пуша
  0.6.0; не перевесил — окно контролируем мы (ops строго после сборки), а несовпадение
  скилл↔образ — тихая поломка у юзера. Цена ошибки: пустой pull до пуша образа, чинится
  порядком ops. Изменил бы выбор: решение Капитана публиковать образ ДО мержа PR.

## Затронутые файлы

- `src/rustok_mcp/gateway.py`, `handlers.py`, `capabilities.py`, `protocol.py`
- `src/rustok_mcp/__init__.py`, `main.py`, `pyproject.toml`, `server.json`,
  `skills/rustok-wallet-tui/claw.json` (версия)
- `skills/rustok-wallet-tui/SKILL.md`, `docs/CONFIGURATION.md`
- `Dockerfile.wallet` (LABEL)
- `tests/test_handlers.py`, `tests/test_gateway.py`, `tests/test_capabilities.py`

## Тест-план (red→green; сюита сейчас 141)

**handlers (`test_handlers.py`):**
1. `execute_transaction` зовёт `GatewayClient.execute_transaction` с `preview_id`,
   ответ проброшен.
2. `execute_transaction` без `preview_id` → invalid params (-32602).
3. `execute_transaction` при `state=pending` — в ответе `next_step` с
   `docker exec -it rustok-wallet-tui rustok-console`.
4. `get_execution_status` зовёт клиента, терминальный ответ (`executed` + `tx_hash`)
   проброшен БЕЗ `next_step`.
5. `get_execution_status` без `preview_id` → invalid params.
6. Оба тула: stub-fallback без клиента.
7. `tools/list` в сессии без `execute_tx` НЕ содержит новых тулов; `tools/call` без
   капабилити → -32001 (паттерн существующих capability-тестов).

**gateway (`test_gateway.py`):**
8. `execute_transaction` шлёт POST на верный путь с телом `{"preview_id": …}` (и БЕЗ
   ключа `approval`).
9. `get_execution_status` шлёт GET с `params={"preview_id": …}`.
10. 404 `{"error":"not_found"}` → `McpError(ERR_NOT_FOUND)`, message проброшен.

**capabilities (`test_capabilities.py`):**
11. `CAPABILITY_MAP` покрывает оба новых тула → `EXECUTE_TX` (дополнить map-тест).

**Существующие тесты, которые ломаются добавлением тулов (обновить в том же PR):**
12. `test_tools_list_handler` (test_handlers.py:113): `len(tools) == 5` → `7`.
    `test_tools_list_filters_by_capability` (len==3 при read_wallet) НЕ ломается — проверено.

**Инвариант приёмки (§Этап 5):** `grep -rn "/run/wallet\|approver.sock" src/rustok_mcp/` —
ноль совпадений (MCP не знает про канал одобрения; команда `docker exec …` в текстах —
не нарушение, это инструкция человеку, не путь к сокету).

## Критерии приёмки — «PR готов, когда…»

- Оба тула зарегистрированы, гейтятся `execute_tx`, ходят на верные роуты; PENDING несёт
  `next_step` с новым именем контейнера; терминальные статусы проброшены как есть.
- `not_found` доходит до агента машинно-читаемым, поллинг останавливаем.
- SKILL.md/CONFIGURATION.md описывают полный flow; нигде не осталось старого имени контейнера;
  CHANGELOG несёт запись `[0.6.0]`.
- Версия 0.6.0 согласована во всех точках реестра §6 (7 version-полей + 8 image-тегов +
  3 Dockerfile-примера + 4 yaml/sh-пина); контрольный греп БЕЗ фильтра расширений:
  `grep -rn "v0\.5\.0\|:0\.5\.0" --exclude-dir=.git --exclude-dir=.venv --exclude-dir=.claude .`
  (вне CHANGELOG-истории) — ноль хитов; LABEL source в Dockerfile.wallet.
- `uv run ruff check` / `uv run mypy` / `uv run pytest` зелёные, вывод приложен; новые тесты
  показаны red→green.

## Definition of Done

- PR смержен в main, ветка удалена.
- Гейты зелёные в CI; до отчёта Гейта-2: fleet-само-ревью (Sonnet 5) без блокеров +
  `/python-review` + `/security-review` (директива Ревьюера Гейта-1: execute-путь кошелька =
  граница доверия, не «просто клиент к роуту»); вердикт Ревьюера «чисто» через Капитана.
- PLAN-OF-RECORD (core) + `workflow-state.json` обновлены на закрытии круга.
