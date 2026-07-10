# Спека: Stage 4 — `rustok-wallet` image с консолью (PR-4)

**Дата:** 2026-07-10 · **Статус:** Gate-1 APPROVED (Captain: «работай шагами») · **База:** `mcp/main` `c92b60c` · **Ветка:** `feat/stage4-wallet-image-console`

## 1. Цель

Слепить из отдельных частей **один Docker-образ кошелька**: ядро + шлюз + MCP + терминальная консоль для человека. После этого команда

```bash
docker exec -it rustok-wallet rustok-console
```

откроет «второе окно», в котором человек видит заявку от агента и жмёт `y/N`.

## 2. Что входит

- `Dockerfile.wallet` копирует бинарник `rustok-console` из `rustok-console:v0.1.0` — по тому же принципу, что `core-server`/`gateway` копируются из `rustok-core:v0.2.0`.
- В образе заранее создан каталог `/run/wallet` (там появится сокет `approve.sock`) с правами `rustok:rustok`.
- `entrypoint.sh` перед стартом ядра делает защитный `mkdir -p /run/wallet`.
- Онбординг-инструкции приведены в соответствие с новой реальностью:
  - мнемоника **12 слов** вместо 24 (решение Капитана Р12);
  - рядом с 12 словами печатается **PIN подтверждения транзакций**;
  - **правило двух окон**: все человеческие операции только в отдельном терминале, агентская сессия их не видит;
  - команда для человека: `docker exec -it rustok-wallet rustok-console`;
  - запуск `docker run` получает фиксированное имя `--name rustok-wallet` (singleton).
- Версия wallet-образа и скилла — **0.5.0** (`pyproject.toml`, `SKILL.md`, `claw.json`, `server.json`, `CHANGELOG.md`).

## 3. Что НЕ входит

- **MCP-тулы `execute_transaction` / `get_execution_status`** — это Этап 5, отдельный PR.
- **UID-split / env-scrub / root-entrypoint** — это v2-hardening, отложено.
- **E2E smoke с реальными docker-образами** — приёмка PR-4, но полный смоук возможен только после публикации `rustok-core:v0.2.0` и `rustok-console:v0.1.0` в GHCR.

## 4. Файлы

| Файл | Изменение |
|---|---|
| `mcp/Dockerfile.wallet` | `ARG CORE_IMAGE` → `v0.2.0`; новый `ARG CONSOLE_IMAGE` → `v0.1.0`; `COPY --from=console`; `/run/wallet` pre-created |
| `mcp/scripts/rustok-wallet-entrypoint.sh` | `mkdir -p "$RUSTOK_DATA_DIR"` уже есть, добавить `mkdir -p /run/wallet`; комментарий 24→12 |
| `mcp/skills/rustok-wallet/SKILL.md` | 24→12, PIN, правило двух окон, `--name`, `docker exec … rustok-console`, версия 0.5.0 |
| `mcp/docs/INSTALL.md` | 24→12, PIN, `--name`, версия образа |
| `mcp/docs/TROUBLESHOOTING.md` | 24→12, forgot-PIN → `core-server set-pin`, name-in-use |
| `mcp/docs/CONFIGURATION.md` | 24→12, упоминание `/run/wallet` |
| `mcp/scripts/install.sh` | 24→12, версия образа |
| `mcp/pyproject.toml` | версия `0.5.0` |
| `mcp/server.json` | версия/образ `v0.5.0` |
| `mcp/skills/rustok-wallet/claw.json` | версия `0.5.0` |
| `mcp/CHANGELOG.md` | секция 0.5.0 с console-интеграцией |

## 5. Критические детали

- **Бинарник консоли** должен лежать в `/usr/local/bin/rustok-console` внутри wallet-образа — туда же, куда кладём `core-server` и `gateway`.
- **Каталог сокета** `/run/wallet` должен быть доступен пользователю `rustok` (uid 1000). Создаём его в Dockerfile с `chown rustok:rustok`, а entrypoint дублирует `mkdir -p` на случай `tmpfs` под podman.
- **TAG по semver:** образы везде `v0.2.0` / `v0.1.0` / `v0.5.0`, никаких `latest`.

## 6. Приёмка

- `ruff check src tests` — clean.
- `mypy src` — clean.
- `pytest` — 137 passed.
- `shellcheck scripts/rustok-wallet-entrypoint.sh` — clean.
- `Dockerfile.wallet` синтаксически валиден (`docker build --no-cache --build-arg CORE_IMAGE=… --build-arg CONSOLE_IMAGE=…` — пропускаем, если удалённые образы ещё не опубликованы; допустимо).
- Не должно остаться упоминаний «24 слова» в доках/скриптах, кроме исторических changelog-записей.

## 7. Зависимости вне PR-4

- Публикация `ghcr.io/rustok-org/rustok-core:v0.2.0` (core PR #90 должен быть смержен и затегирован).
- Публикация `ghcr.io/rustok-org/rustok-console:v0.1.0` (console PR #5 должен быть смержен и затегирован).
- Эти шаги — за Капитаном; сам PR-4 к ним готовится заранее.
