# Спека: fix-PR по ре-ревью Этапа 4 (claw.json + wallet-publish + доки)

**Дата:** 2026-07-10 · **Статус:** ратифицирован Капитаном («делай фикс-PR») · **База:** `mcp/main` `8a40956` · **Ветка:** `fix/stage4-review-followups`

## 1. Контекст

Ре-ревью Этапа 4 (#57) нашло: сессия при реализации рвалась, финальный коммит дорабатывала
другая модель. Подтверждённые дефекты — 2 блокера + 2 минора. Этот PR закрывает их и ничего
больше (релизный поезд, Этап 5, podman-hardening — НЕ здесь).

## 2. Дефекты → фиксы

### Ф1 (БЛОКЕР): `skills/rustok-wallet/claw.json` уничтожен
Файл на main байт-в-байт равен `server.json` (MCP-registry формат) — потеряны все
ClawHub-поля. Спека Этапа 4 §4 требовала только бамп версии.
**Фикс:** восстановить из `8a40956^:skills/rustok-wallet/claw.json` (формат 0.4.4) с двумя
изменениями:
- `version`: `0.4.4` → `0.5.0`;
- `description`: добавить предложение про approval-console, зеркаля новый SKILL.md, но во
  втором лице (голос claw-манифеста): «Transactions that move funds require your approval in
  a separate terminal console, never inside the agent chat.»
Остальные поля (`author`, `license: MIT-0`, `permissions: ["network"]`, `entry: SKILL.md`,
`tags`, `minOpenClawVersion: 0.8.0`, `homepage`) — вербатим из 0.4.4.

### Ф2 (БЛОКЕР): `wallet-publish.yml` не соберёт 0.5.0
Три дефекта: (а) `CORE_IMAGE=…rustok-core:${{ github.ref_name }}` переопределяет правильный
дефолт Dockerfile несуществующим тегом; (б) `type=semver` от git-ref при `workflow_dispatch`
с ветки даёт пустые tags → build-push падает; (в) комментарий-шапка описывает старую
реальность (`rustok-core:<wallet-tag>`).
**Фикс:**
- `workflow_dispatch` получает обязательный input `version` (описание: «digits only, без
  ведущего v, например 0.5.0; должна совпадать с pyproject.toml»);
- guard-шаг до сборки: version из `pyproject.toml` сравнивается с input, расхождение = fail
  (класс дрейфа уже случался в репо: SKILL.md 0.3.2 при 0.4.x-линии; ловит и ведущий `v`);
- tags: `type=semver,pattern=…,value=v${{ inputs.version }}` — каскад `vX.Y.Z`/`vX.Y`/`vX`
  сохранён (конвенция rustok-core и старых wallet-тегов `v0.1.2/v0.1/v0`); синтаксис `value=`
  подтверждён документацией metadata-action (/check Finding 5);
- блок `build-args` с `CORE_IMAGE` удалить целиком — пины базовых образов живут ТОЛЬКО в
  `Dockerfile.wallet` (v0.2.0/v0.1.0), один источник истины;
- шапку-комментарий переписать: workflow остаётся manual-only; предусловия запуска —
  `rustok-core` package в GHCR должен быть **Public** (предусловие из core #90; на
  2026-07-10 он private — ops Капитана) и `rustok-console:v0.1.0` опубликован. Fallback —
  ручная сборка+push с dev-машины (как v0.4.0).

### Ф3 (МИНОР): CONFIGURATION.md без упоминания `/run/wallet`
Требование спеки Этапа 4 §4 не выполнено.
**Фикс:** короткая секция «Approval console»: сокет `/run/wallet/approve.sock` внутри
контейнера (создаётся образом, НЕ volume и НЕ настройка пользователя); человек подтверждает
через `docker exec -it rustok-wallet rustok-console` во втором терминале. Env-таблицу НЕ
расширять (`RUSTOK_APPROVE_SOCK` не документируем: смена пути ломает консоль в том же
контейнере — приглашение к мисконфигу).

### Ф4 (снят до подтверждения): shellcheck
/check Finding 1: CI УЖЕ гоняет `shellcheck scripts/*.sh` (`ci.yml:43-50` +
`test-distribution.yml:18-28`), оба зелёные на мерже #57 → entrypoint уже clean. Претензия
ре-ревью справедлива только к тексту PR-отчёта («sh -n»), не к фактическому покрытию.
**Фикс:** установить shellcheck локально (`sudo dnf install -y ShellCheck`), прогнать на
`scripts/*.sh` для подтверждения (ожидание: clean, 0 правок). Правки файла — только если
ожидание неверно.

### Ф5 (доп. скоуп, ратифицирован Капитаном 2026-07-10): регрессионный гард claw.json
Единственная выжившая находка fleet-ревью (suggestion): CI никак не валидирует claw.json —
дыра, пропустившая исходный дефект. **Фикс:** `tests/test_claw_manifest.py` — парсится как
JSON; ClawHub-ключи присутствуют (name/version/entry/permissions/minOpenClawVersion + author/
license/tags/homepage); server.json-ключей нет ($schema/packages/websiteUrl/repository);
`name == "rustok-wallet"`; `entry` указывает на существующий файл; версия == pyproject.
Red-доказательство: прогон против server.json-содержимого (артефакт исходного дефекта).

## 3. Что ЯВНО не входит

- Релизный поезд (теги core/console, публикация образов, переключение видимости
  rustok-core → Public) — ops Капитана / следующий шаг плана.
- Этап 5 (MCP-тулы), Этап 6 (E2E), podman-tmpfs hardening, upgrade-путь старых volume.
- Правки `server.json`, `Dockerfile.wallet`, `SKILL.md`, `smithery.yaml` — там дефектов нет.
- Существующий тег `latest` на rustok-wallet в GHCR (указывает на 0.4.0) — вопрос
  релизного поезда.
- Фраза «losing all three» в CONFIGURATION.md — стилистический нит, не трогаем (rules #12).

## 4. Файлы

| Файл | Изменение |
|---|---|
| `skills/rustok-wallet/claw.json` | восстановление ClawHub-формата + 0.5.0 + description |
| `.github/workflows/wallet-publish.yml` | input `version`, tags value=, минус CORE_IMAGE-override, шапка |
| `docs/CONFIGURATION.md` | секция «Approval console» с `/run/wallet` |
| `scripts/rustok-wallet-entrypoint.sh` | только если shellcheck найдёт error/warning |

## 5. Приёмка

- `python3 -m json.tool skills/rustok-wallet/claw.json` — валиден; поля 1:1 с 0.4.4
  кроме `version`/`description` (доказать diff'ом против `8a40956^`).
- В claw.json НЕТ полей server.json-схемы (`$schema`, `packages`, `websiteUrl`, `repository`).
- YAML wallet-publish валиден: `python3 -c yaml.safe_load` + построчное ревью диффа
  (actionlint на машине нет — /check Finding 4).
- `shellcheck scripts/*.sh` — clean (подтверждение, правок не ожидается).
- `pytest` / `ruff` / `mypy` — зелёные (код src/ не трогаем, но гейт прогоняем — rules #8).
- `grep -c 'run/wallet' docs/CONFIGURATION.md` ≥ 1.
- Версия 0.5.0 в claw.json выше ClawHub-листинга (0.4.3) — требование веб-заливки.

## 6. Риски

- `docker/metadata-action` v6: атрибут `value=` у `type=semver` — штатный способ подать
  версию не из git-ref (документация action, применяется при dispatch). Проверить
  синтаксис по пиненной версии action в workflow.
- ClawHub может иметь недокументированные обязательные поля сверх 0.4.4-набора — но
  0.4.4-набор уже проходил веб-заливку (листинг v0.4.3 жив), значит достаточен.
