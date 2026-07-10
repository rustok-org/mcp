# Спека: переименование консольной линии в rustok-wallet-tui

**Дата:** 2026-07-10 · **Статус:** ратифицировано (ADR `core/.claude/decisions/2026-07-10-two-products-naming.md`, вердикт B′ + имя Капитана; «продолжай» = go) · **База:** `mcp/main` `efdb193` · **Ветка:** `feat/rename-tui-product`

## 1. Контекст

Два продукта под одним именем = путаница (ратификация Капитана 2026-07-10). Публичная
идентичность `rustok-wallet` принадлежит агентской линии (сайт, ClawHub v0.4.4, MCP Registry
v0.4.0, `latest`). Консольная линия (main, 0.5.x) переименовывается в **`rustok-wallet-tui`**
СЕЙЧАС, пока у неё 0 пользователей (релиз вчера, не анонсирован).

## 2. Инварианты переименования

- **Продукт** (образ, скилл, контейнер, volume, реестр-имя): `rustok-wallet` → `rustok-wallet-tui`.
- **Компоненты НЕ трогаются:** бинарь/репо `rustok-console`, python-пакет `rustok-mcp`,
  файл `scripts/rustok-wallet-entrypoint.sh` (имя файла — внутренность образа; только
  строки-префиксы логов в нём).
- **История НЕ переписывается:** CHANGELOG-записи ≤0.4.x (агентская линия) и git-теги
  `wallet-v0.4.0`, `skill-v0.4.x` — как есть. В секцию 0.5.0 — примечание о переименовании.
- **Версия остаётся 0.5.0** (потребителей нет; docs уже пиннят v0.5.0 — меняется только имя).
- Volume в доках: `-v rustok-wallet:/data` → `-v rustok-wallet-tui:/data` (у двух продуктов
  на одной машине НЕ должен быть общий keystore-volume: разные core-линии).

## 3. Файлы (по карте grep, 16 файлов)

| Файл | Что |
|---|---|
| `skills/rustok-wallet/` → `skills/rustok-wallet-tui/` | git mv; claw.json `name`, description при необходимости; SKILL.md frontmatter `name` + все run-команды |
| `server.json` | `name: io.github.rustok-org/rustok-wallet-tui`, identifier `…/rustok-wallet-tui:v0.5.0` |
| `Dockerfile.wallet` | LABEL title + `io.modelcontextprotocol.server.name` (= server.json name!), комментарии-примеры |
| `.github/workflows/wallet-publish.yml` | `IMAGE_NAME: …/rustok-wallet-tui`, labels title |
| `docs/{INSTALL,CONFIGURATION,TROUBLESHOOTING}.md` | образ, `--name`, volume, `docker exec -it rustok-wallet-tui rustok-console` |
| `smithery.yaml` | образ, volume, `--name` |
| `scripts/install.sh` + `skills/…/scripts/health-check.sh` | IMAGE-дефолт, run-команды |
| `scripts/rustok-wallet-entrypoint.sh` | только лог-префиксы `rustok-wallet:` → `rustok-wallet-tui:` |
| `tests/test_claw_manifest.py` | путь скилла + assert name == "rustok-wallet-tui" |
| `README.md` | секция «Two editions»: rustok-wallet (agent, его живые каналы — ClawHub/Registry-ссылки строки 30/35/36/39 переезжают ТУДА как ссылки агентской версии) vs rustok-wallet-tui (этот main); install-команда :26 → rustok-wallet-tui (/check F1) |
| `CHANGELOG.md` | секция 0.5.0 = tui-продукт: обновить имя + строка «Renamed to rustok-wallet-tui…»; записи 0.4.x и старше (агентская история) НЕ трогать (/check F2) |
| `.dockerignore` | НЕ трогать (:17 = имя файла entrypoint) |

**Запрет:** никакого repo-wide sed — только per-file правки; `rustok-wallet-entrypoint`
(имя файла в Dockerfile COPY и .dockerignore) не переименовывается (/check F3).
Grep-приёмка §5 получает whitelist: `rustok-wallet-entrypoint`.

## 4. После merge (пост-шаги, вне PR)

1. Пересборка образа из main → push `ghcr.io/rustok-org/rustok-wallet-tui:{v0.5.0,v0.5,v0}` (podman).
2. Смоук нового образа (бинари, tty-гейт).
3. **Удалить** мои вчерашние артефакты с 0 потребителей (восстановимы: локальный podman-образ + git-история): GHCR-теги `rustok-wallet:{v0.5.0,v0.5,v0}` и git-тег `wallet-v0.5.0` → новый git-тег `wallet-tui-v0.5.0` на merge-коммите. ⚠️ Удаление GHCR-версий требует скоупа `delete:packages`, у токена его НЕТ (/check F4): либо `gh auth refresh -s delete:packages` (device-код вводит Капитан), либо удаление версий Капитаном в веб-UI пакета. Не блокирует публикацию tui-образа.
3b. Новый ClawHub-листинг: Капитану задать title с keyword (напр. «Rustok TUI Wallet — human-approved Ethereum agent wallet») — [[clawhub-skill-discoverability]] (/check F6).
4. `latest` у `rustok-wallet` НЕ трогается (заморожен на v0.4.0 — ADR).
5. Ops Капитана (не мои): новая запись MCP Registry (`mcp-publisher`, device-flow), новый ClawHub-листинг для tui.

## 5. Приёмка

- `grep -rn 'rustok-wallet' --exclude-dir={.git,.claude} --exclude=uv.lock .` — каждое
  оставшееся вхождение объяснимо: история CHANGELOG/README-агентское/`rustok-wallet-tui`-подстрока/имя файла entrypoint.
- server.json `name` == Dockerfile LABEL `io.modelcontextprotocol.server.name` (валидатор реестра).
- Гейты: ruff/format/mypy/pytest (141) + shellcheck + json/yaml-валидность.
- `/review` чист.

## 6. Риски

- Пропущенное вхождение имени → путаница остаётся: закрывается grep-приёмкой §5.
- Смешение продуктовых и компонентных имён (`rustok-console` бинарь) — инвариант §2.
- skills-tap: `npx skills add rustok-org/mcp` после merge ставит скилл под новым именем —
  намеренно (main = tui-продукт).
