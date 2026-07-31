# Task 0 — Appendix: слепая установка rustok-wallet (agent edition) глазами пользователя

Дата: 2026-07-30. Метод: «слепой» пользователь без доступа к исходникам, только публичные каналы
(лендинг https://rustokwallet.com, листинг ClawHub `temrjan/rustok-wallet`, MCP Registry, GHCR).
Все команды выполнялись реально; рабочая папка — `/tmp/rustok-blind-install`.
Реальные деньги не использовались; `execute_send` не вызывался.

## Хронологический протокол

### Шаг 0. Инструменты на машине

```
docker  : NOT FOUND
podman  : 5.8.4   skopeo: 1.22.2
claude  : 2.1.220 (Claude Code), ~/.local/bin/claude
node    : v24.18.0   npm/npx: 11.16.0
python3 : 3.14.6   curl: 8.18.0   jq: 1.8.1
```

Вердикт: **трение** — лендинг для agent edition требует «Docker running», docker на машине нет.

### Шаг 1. Лендинг → инструкции agent edition

Извлечён текст https://rustokwallet.com (секция `#install-agent`):

- 01 `create-wallet`: `docker run -it --rm -v rustok-wallet:/data -e RUSTOK_KEYRING_PASSWORD="..." ghcr.io/rustok-org/rustok-wallet:latest create-wallet`
- 02 JSON-конфиг для MCP-клиента с `"command": "docker"`.

Вердикт: ок (инструкции найдены).

### Шаг 2. Сверка публичных каналов

- MCP Registry: `io.github.rustok-org/rustok-wallet` v0.4.0, OCI `ghcr.io/rustok-org/rustok-wallet:v0.4.0`, stdio, runtimeHint `docker` — согласуется с лендингом. **Ок.**
- ClawHub `temrjan/rustok-wallet`: описывает **другой продукт** — HTTP-сервис `rustok-agent-mcp` на `127.0.0.1:3000`, образ `ghcr.io/temrjan/rustok-agent-mcp`, другой репозиторий (`temrjan/rustok`), install-скрипт `install-agent-mcp.sh`, testnet-only. С лендингом (stdio-образ `rustok-org/rustok-wallet`, mainnet по умолчанию) не стыкуется. Вердикт: **трение (косметика→среднее)** — пользователь не понимает, какой из двух артефактов «тот самый».

### Шаг 3. Шаг 01 буквально — БЛОКЕР

```
$ docker run -it --rm -v rustok-wallet:/data ... create-wallet
/bin/bash: docker: command not found   (exit=127)
```

Вердикт: **блокирует установку** при буквальном следовании. Лендинг не упоминает podman для agent edition
(podman упомянут только в console edition и в INSTALL.md).

### Шаг 4. Обход №1: podman вместо docker

```
$ skopeo inspect docker://ghcr.io/rustok-org/rustok-wallet:latest   → ок, публичный, linux/amd64
$ podman pull ghcr.io/rustok-org/rustok-wallet:latest               → ок (223 MB)
$ podman run -it --rm -v rustok-wallet:/data -e RUSTOK_KEYRING_PASSWORD="choose-a-strong-password" \
    ghcr.io/rustok-org/rustok-wallet:latest create-wallet
warning: The input device is not a TTY...
======================  NEW AGENT WALLET  ======================
Address:  0xe99a7aa370129777105C012313533564f368f881
Recovery phrase (24 words) — WRITE IT DOWN, SHOWN ONLY ONCE: [показана]
exit=0
```

Вердикт: **ок с оговорками** — кошелёк создан; podman ругается на отсутствие TTY, но не падает
(в отличие от `rustok init` console edition, который отказывается без TTY — задокументировано в INSTALL.md).
Тестовый пустой кошелёк: `0xe99a7aa370129777105C012313533564f368f881`, volume `rustok-wallet`.

### Шаг 5. Шаг 02 буквально — регистрация в Claude Code с `"command":"docker"`

```
$ claude mcp add-json rustok-wallet '{"command":"docker","args":[...],"env":{...}}'  → Added (local scope)
$ time claude mcp list
rustok-wallet: ... - ✘ Failed to connect — ENOENT: Executable not found in $PATH: "docker"
real 0m6.3s
```

Вердикт: **блокер** (тот же корень, что шаг 3), но диагностика честная и быстрая.

### Шаг 6. Обход №2: конфиг с `"command":"podman"` — тихий таймаут

```
$ claude mcp add-json rustok-wallet '{"command":"podman","args":[run,-i,--rm,--init,...]}'
$ time claude mcp list
rustok-wallet: ... - ✘ Failed to connect — MCP server "rustok-wallet" connection timed out after 30000ms
real 0m32.4s
```

Вердикт: **блокер**. Воспроизводится стабильно (3 прогона, всегда ровно 30 с таймаут + ~2 с накладных).

### Шаг 7. Внешняя диагностика: ручной JSON-RPC в stdio контейнера

```
$ { echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{...}}'; sleep 20; } | \
    podman run -i --rm --init -v rustok-wallet:/data -e ... ghcr.io/rustok-org/rustok-wallet:latest
→ ответ на stdout через 3.9 с:
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","capabilities":{"tools":{}},
 "serverInfo":{"name":"rustok-mcp","version":"0.4.0"},"instructions":"...донаты..."},"error":null}
```

Полный обмен `initialize` + `notifications/initialized` + `tools/list` — работает, 8 инструментов
(`get_wallet_context`, `get_balances`, `get_positions`, `preview_send`, `execute_send`,
`preview_transaction`, `execute_transaction`, `get_execution_status`, `sign_message` — фактически возвращён
список; capability-набор соответствует таблице на лендинге).

Вердикт: сервер **исправен**, проблема на стыке с клиентом.

### Шаг 8. Wrapper-сниффер между Claude и контейнером

Конфиг с `"command":"/tmp/rustok-blind-install/podman-wrapper.sh"` (tee stdin/stdout в логи):

- Claude Code 2.1.220 шлёт: `initialize` с `protocolVersion:"2025-11-25"`, capabilities `{roots, elicitation}`.
- Сервер отвечает (клиенту ответ **доставлен**): `protocolVersion:"2024-11-05"` + поле `"error":null`.
- После этого Claude молчит 30 с и отваливается по таймауту; `notifications/initialized` не отправляет.

### Шаг 9. Изоляция root cause (MITM-прокси `/tmp/rustok-blind-install/mcp-version-proxy.py`)

| Прогон | Что патчим в ответах сервера | Результат `claude mcp list` |
|---|---|---|
| A | только `protocolVersion` → 2025-11-25 | ✘ таймаут 30 с |
| B | версия + удаление `"error":null` | ✔ Connected за 6.5 с |
| C | **только удаление `"error":null`** (версия оставлена 2024-11-05) | ✔ Connected за 6.5 с |

**Root cause: нестандартное поле `"error":null` в каждом JSON-RPC ответе сервера.**
Ответ одновременно содержит `result` и `error` (пусть и null) — это нарушает JSON-RPC 2.0
(«response MUST contain either result or error, not both») и не проходит валидацию схемы
в MCP SDK клиента: сообщение молча отбрасывается → «тихий таймаут».
`protocolVersion: 2024-11-05` сам по себе Claude Code 2.1.220 принимает — версия НЕ является причиной.

### Шаг 10. Сквозная проверка через Claude (с прокси)

```
$ echo "Call get_wallet_context..." | claude -p --allowedTools "mcp__rustok-wallet__get_wallet_context"
→ Address: 0xe99a7aa370129777105C012313533564f368f881; chains 1, 8453; балансы пустые.
```

Инструмент вызывается, данные возвращаются. Побочное наблюдение: поле `instructions` сервера
содержит встроенную просьбу о донате с конкретным ETH-адресом — Claude помечает это как
prompt-injection-подобный контент (вердикт: **трение/безопасность UX**, см. сводку).

### Шаг 11. Финальное состояние

Конфиг возвращён к «честному» виду (`"command":"podman"`, без прокси) → `claude mcp list` снова
таймаут 30 с. Осиротевших контейнеров не осталось (`podman ps -a` чист, `--rm` отработал).
Volume `rustok-wallet` с тестовым кошельком оставлен на машине.

## Сводка точек трения

| # | Точка трения | Severity |
|---|---|---|
| 1 | Agent edition требует `docker`; на podman-only машине буквальная установка умирает на шаге 01 (`command not found`) | **Блокирует установку** (обход: s/docker/podman/ — работает, но не задокументирован для agent edition) |
| 2 | MCP-сервер возвращает `"error":null` рядом с `result` в каждом ответе → MCP SDK клиента отбрасывает ответ → хэндшейк с Claude Code всегда падает тихим таймаутом ровно 30 с, без какой-либо диагностики причины | **Блокирует подключение** (продуктовый баг образа v0.4.0; обхода пользовательскими средствами нет, кроме патча-трафика проксей) |
| 3 | ClawHub-листинг `temrjan/rustok-wallet` описывает другой артефакт (HTTP `rustok-agent-mcp`, другой GHCR-namespace, другой репо) — конфликтует с лендингом и MCP Registry | Требует обхода (выбрать «какой инструкции верить») |
| 4 | `-it` в команде create-wallet при запуске без TTY даёт warning podman; в агентском шелле пугает, но не ломает | Косметика |
| 5 | `instructions` сервера содержит донат-просьбу с адресом — выглядит как prompt-injection в метаданных инструментов, клиенты это флагают | Косметика/доверие |
| 6 | Registry пинает `v0.4.0`, лендинг — `latest` (сейчас совпадают по digest, но расходятся при следующем релизе) | Косметика |

## Финальный вердикт

**MCP-сервер НЕ подключается к Claude Code «из коробки».** Установка останавливается на шаге
«подключить MCP»: после обхода отсутствия docker (podman) хэндшейк стабильно умирает тихим
30-секундным таймаутом из-за нестандартного поля `"error":null` в JSON-RPC ответах образа
`ghcr.io/rustok-org/rustok-wallet:latest` (= v0.4.0, digest `sha256:bb392167…38654`).
Кошелёк создать удалось (пустой тестовый, адрес выше), инструменты работают — это доказано
через патч-прокси, удаляющий `"error":null`: после него `✔ Connected` за ~6.5 с и
`get_wallet_context` возвращает корректные данные. Исправление — однострочное на стороне
сервера (не эмитить `error` при успехе), но пользовательскими средствами не выполнимо.

Проверено реальными командами; всё, что не выполнялось, выше не утверждается.
В пределы таймаута уложился полностью.

## Приложение: версии инструментов

- podman 5.8.4; skopeo 1.22.2 (commit c766fdc4)
- claude 2.1.220 (Claude Code)
- node v24.18.0, npm/npx 11.16.0
- python3 3.14.6, curl 8.18.0, jq 1.8.1
- docker — отсутствует
- ОС: Linux x86_64 (Fedora-based), rootless podman
- Образ: `ghcr.io/rustok-org/rustok-wallet:latest` = v0.4.0, digest `sha256:bb3921675711dac6ef23a738ed43d9f8a07b43e8c7659d0c7847f7a36aa38654`, serverInfo `rustok-mcp 0.4.0`

Артефакты диагностики (в /tmp, не в репо): `/tmp/rustok-blind-install/` —
`podman-wrapper.sh`, `mcp-version-proxy.py`, `wrapper.*.log`, `proxy.log`, `INSTALL.md`, `landing.html`.
