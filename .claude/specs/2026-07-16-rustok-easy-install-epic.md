# Эпик: rustok easy-install — «одна команда, всё из коробки»

> Статус: **ПЛАН, раунд-1 правок Гейта-1 вшит; ждёт второй подписи.** Кода нет до ратификации.
> Триггер: первый живой пользователь (2026-07-15) прошёл семь болячек установки руками;
> инцидент Hermes (кошелёк не виден) — тот же корень. Ресёрч ведущих инсталлеров (Ollama/uv/
> rustup/Homebrew/Bun/Deno/Docker/Smithery) + форензик Hermes — в основе.
> Команда: Капитан/Инженер/Ревьюер; связь через Капитана. Репо: `mcp` (главный) + новый
> `homebrew-rustok` (fast-follow). Каждый PR — свой круг гейтов.

## Гейт-1, раунд 1 — что изменилось (аудит-дельта)

- **Б-1:** подпись перенесена в `wallet-publish.yml` (там строится кошелёк), НЕ в
  `docker-publish.yml` (там `rustok-mcp`); + `id-token: write` для keyless-cosign; ручной
  laptop-publish получил signing-runbook. PR-3.1 переписан.
- **Б-2:** решение #4 конфликтовало с discovery по единственной метке. Введена суб-метка
  `rustok.agent=<name>` + `rustok console --agent`; при N>1 — громкий отказ со списком,
  никогда «первый попавшийся». PR-2.1 и Стадия 0 обновлены.
- **Б-3:** macOS требует arm64-образа (сейчас linux/amd64 only) + podman-machine. v1 =
  **Linux/amd64**; macOS + Homebrew — вынесены в **Стадию 5 (fast-follow v1.1)**.
- **М-1:** проба доказала, что «образ принимает secret» — пустой дифф. PR-1.1 переписан на
  реальное содержимое: `RUSTOK_KEYRING_PASSWORD_FILE` (~5 строк entrypoint) → паритет
  podman(`type=mount`)/docker(0600-файл), plaintext нигде.
- **М-2:** RPC-URL с ключом провайдера — второсортный секрет; PR-2.3a задаёт ему дом.
- **М-3:** детерминизм движка (podman/docker), идемпотентность `init`, полнота `uninstall`.
- **М-4:** тест-план ужесточён (строгие ассерты per `assert_resident`, не только «pty живёт»).
- **М-5:** PR-2.3 разбит на 2.3a/b/c; PR-3.1 помечен параллелизуемым с 1-го дня.
- **НИТы:** цитата `entrypoint:35`→честная (читает core-server, доказано пробой); `printf %s`
  только builtin; `--secret` — аргумент podman не claude; шим self-update = re-run curl|sh;
  sha256 install.sh + откат; инвариант «install.sh НИКОГДА не касается секрета/кошелька».

### Гейт-1, раунд 2 (вторая подпись — APPROVED WITH NITS) — вшито

- **МИНОР (RPC-механизм не работал):** образ env-файлы не парсит + rootless-podman отдаёт
  хостовый 0600-файл как root-owned (uid 1000 не прочитает). Фикс: RPC на podman —
  тем же доказанным `--secret rustok-rpc-<agent>,type=env,target=RUSTOK_RPC_URLS_*` (ноль новых
  механизмов); на docker-фолбэке — честный bare `-e` (второй класс, tier-примечание). Tier
  сохранён (пароль=secret везде; RPC=secret/podman, bare-e/docker).
- **НИТ-1:** Hermes-runbook выписывает ОБЕ метки (`rustok=wallet` И `rustok.agent=hermes`) —
  discovery фильтрует по обеим, иначе Hermes снова невидим (реинкарнация бага).
- **НИТ-2:** state-файл движка сразу зовётся `~/.config/rustok/config` (единственный, второй
  плодить не будем).
- **ТВОЙ ВЫБОР (инфра, принят):** `install.sh` ставится с **GitHub raw по immutable-тегу**
  (`raw.githubusercontent.com/rustok-org/mcp/vX.Y.Z/scripts/install.sh`), НЕ с `get.rustok.org`.
  Минус ops-пункт (домен/хостинг/его безопасность), инсталлер аудируем в репо по тегу,
  version-pin бесплатно из git-тега. `get.rustok.org` — позже редиректом (бэклог бренда).

## Цель — один абзац

Свести установку и запуск кошелька к **одной команде `rustok`** по форме Ollama (фоновый
сервис-контейнер + короткий клиент): `curl|sh` ставит закалённый шим `rustok` в
`~/.local/bin`, а `rustok init/connect/…` берёт на себя всё ручное — создание кошелька с
безопасным паролем (через secret/файл, не env-file-с-кавычками), авто-регистрацию MCP у
агента (Claude/Cursor/Hermes, каждому свой кошелёк по суб-метке), запуск консоли одобрения,
обновление и удаление. Планка кошельковая: digest-пин + cosign-подпись, plaintext нигде,
Homebrew вторым каналом (fast-follow).

## Скоуп v1 — что входит / что ЯВНО не входит

**Входит (v1, Linux/amd64):** шим `rustok`; закалённый `install.sh`; переход секретов на
`podman secret`/`_FILE` (уход от `--env-file`); cosign-подпись в `wallet-publish.yml` +
digest; переписанные INSTALL/TROUBLESHOOTING/SKILL; тесты шима/инсталлера; исправление
`--name`-бага (discovery по метке+суб-метке).

**ЯВНО НЕ входит:** **macOS/arm64 + Homebrew-tap → Стадия 5 (fast-follow v1.1)** — нужен
arm64-билд кошелька + podman-machine-ветка; не гейтит Linux-победу. Демон-арбитр общего
кошелька — Фаза 3 (здесь каждый агент СВОЙ кошелёк). Зашифрованный secret-драйвер/OS-keychain
— апгрейд-путь помечен (дефолт podman file-driver = base64, честно как «не крипто-стойкость»).
Windows. GUI. core-код (ноль).

## Решения к ратификации — предрешены (обновлены раундом-1)

1. **Два канала: `curl|sh` (основной, Linux v1) + Homebrew-tap (fast-follow v1.1).** curl|sh
   привычен, убирает 7 болячек; brew — аудируемый канал для не-пайп-в-shell; риск снят
   digest+подпись+function-wrap+версионный-URL+inspect-before-run. Инвариант, делающий curl|sh
   приемлемым для кошелька: **install.sh НИКОГДА не касается секрета/ключей/кошелька** —
   money-критичное (create-wallet, secret, approve) в пайп-скрипт не попадает.
2. **Секрет через `podman secret` (`type=mount`/`type=env`) или `RUSTOK_KEYRING_PASSWORD_FILE`,
   НИКОГДА `--env-file`/bare `-e`.** Проба (2026-07-16, эфемерно): `type=env` инъектит пароль
   с кавычками/`$`/`'` байт-в-байт, `podman inspect` его не показывает — VERIFIED. Docker-паритет:
   **`_FILE`-конвенция** (смонтированный 0600-файл), не bare `-e` (тот утёк бы в `docker inspect
   Config.Env` и в MCP-JSON). Дефолт podman file-driver = base64 — честно в доках, encrypted-
   driver/keychain в бэклоге, не выдаём за крипту.
3. **Шим = POSIX-shell-скрипт.** Проверенный минимум (Ollama/rustup). Переключатель: если шим
   начнёт держать состояние/сложный парс — Rust-бинарь.
4. **Мультиагент = каждому свой кошелёк (свой volume/ключ) + своя суб-метка
   `rustok.agent=<name>`.** Форензик: общий volume включает nonce-дроп + маршрутизацию не в
   тот контейнер (Фаза 3). Discovery: `rustok` фильтрует `label=rustok=wallet` И
   `rustok.agent=<name>`; при неоднозначности (N>1 без `--agent`) — **громкий отказ со списком
   агентов**, никогда первый матч. Стадия 0 даёт Hermes `rustok.agent=hermes` + volume
   `rustok-hermes`.
5. **Digest-пин + cosign-подпись в `wallet-publish.yml`** (не docker-publish — там другой
   образ). `@sha256:…`, не только `:v0.7.1`. Заодно закрывает бэклог «mutable-теги vs digest».
   Предусловие (ops): core-пакет публичным + cosign-identity + `id-token: write` в workflow.
6. **Podman-first (rootless), docker — фолбэк с `_FILE`.** Движок выбирается детерминированно
   (podman если есть, иначе docker) и **липко** (том per-engine — записать выбор в
   `~/.config/rustok/config`, не перевыбирать молча).

## Архитектура (кратко, с правками раунда-1)

- **`rustok` шим** (`mcp/cli/rustok` → `~/.local/bin`): движок из state-файла; discovery
  `--filter label=rustok=wallet --filter label=rustok.agent=<name>`; `console`/без-арг =
  exec-or-start-detached (`-d -i --label rustok=wallet --label rustok.agent=<name>`, НИКОГДА
  `--name`); N>1 без `--agent` → `error: multiple wallets running: claude, hermes — use --agent`.
- **Секрет-инвокация**: podman — `--secret rustok-keyring-<agent>,type=env,target=RUSTOK_KEYRING_PASSWORD`;
  docker — `-v <0600-file>:/run/secret:ro -e RUSTOK_KEYRING_PASSWORD_FILE=/run/secret`.
- **RPC-URL** (второсортный секрет, М-2 + раунд-2): podman — `--secret rustok-rpc-<agent>,
  type=env,target=RUSTOK_RPC_URLS_*` (тот же доказанный механизм, ноль правок образа); docker —
  честный bare `-e` (второй класс: локальный inspect того же юзера, tier-примечание). Пароль
  остаётся secret/`_FILE` на обоих движках.
- **`install.sh`** (`raw.githubusercontent.com/rustok-org/mcp/vX.Y.Z/scripts/install.sh` —
  immutable-тег, аудируем в репо; `get.rustok.org` позже редиректом): `main(){…}; main "$@"`;
  `curl --proto '=https' --tlsv1.2 -fsSL`; `podman pull …@sha256:<digest>` + `cosign verify`;
  копия шима; PATH (`RUSTOK_NO_MODIFY_PATH`); опубликованный sha256; «inspect-before-run» в доке.

## Стадии → PR

### Стадия 0 — Hermes-разблок (независимая, ценность сразу)
Форензик: обёртка ломает протокол (0 инструментов), Hermes держит сессию сам → **обёртку
удалить, дать Hermes СВОЙ кошелёк** (volume `rustok-hermes`, суб-метка `rustok.agent=hermes`).
- **PR-0.1 (репо docs):** починить `--name`-баг в `mcp/docs` (discovery по метке, не фикс.имя)
  + раздел «второй агент = свой кошелёк + своя суб-метка». Тест: греп-инвариант доков.
- **Ops Капитана (runbook в отчёте):** удалить `~/.hermes/scripts/rustok-mcp-server.py`;
  прямой `podman run … -v rustok-hermes:/data --label rustok=wallet --label rustok.agent=hermes …`
  (ОБЕ метки — discovery фильтрует по обеим, иначе Hermes невидим шиму); `create-wallet` для
  Hermes; `enabled: true`.

### Стадия 1 — Секрет-фундамент (образ + entrypoint + доки)
- **PR-1.1 (реальный дифф ~5 строк, М-1):** entrypoint читает `RUSTOK_KEYRING_PASSWORD_FILE`,
  если env-var не задан → включает podman `type=mount`-secret и docker-паритет через 0600-файл.
  Тесты: проба ОБА движка (init→connect→approve цикл), **plaintext отсутствует в `inspect`/
  MCP-JSON** (строгий ассерт), негатив «нет секрета → именованная ошибка», «кавычки в секрете
  не ломают». Пруф: pty против образа.
- **PR-1.2:** доки/MCP-примеры → secret/`_FILE`; `--env-file` legacy; discovery по метке.

### Стадия 2 — Шим `rustok`
- **PR-2.1:** ядро шима + `console`/без-арг с **per-agent discovery** (суб-метка, `--agent`,
  **отказ-со-списком при N>1**), `status`, `doctor` (детект podman/docker + PATH + подсказки).
  Тесты: bats/shell на стаб-контейнерах, shellcheck; строгий ассерт «два контейнера →
  именованная ошибка, не первый матч».
- **PR-2.2:** `init` (интерактив: `read -rs` ×2 → секрет через `printf %s` как **builtin**,
  не в argv; seed+PIN один раз), `start`/`stop`. Идемпотентность: существующий секрет → отказ
  с сообщением, `--force` = rm+recreate. Тесты: init против стаба, секрет создан, повтор без
  `--force` отказывает.
- **PR-2.3a (М-2, М-5):** `connect claude` — авто-регистрация (`claude mcp add -s user rustok
  -- podman run … --secret …` — всё после `--` = аргументы **podman**), точный JSON-ассерт,
  per-agent суб-метка + свой volume; **RPC-URL: podman — `--secret rustok-rpc-<agent>,type=env`;
  docker — bare `-e` (tier-примечание)**. Тест: `claude mcp list → Connected`; на podman ассерт
  что RPC-ключ НЕ в `~/.claude.json`; на docker — tier задокументирован.
- **PR-2.3b:** `connect cursor` (запись `~/.cursor/mcp.json`) + `connect hermes` (свой volume/
  суб-метка — оформляет Стадию 0 в команду). Тесты: точный JSON обоих.
- **PR-2.3c:** `update` (следующий digest + перерегистрация; **шим self-update = re-run curl|sh,
  задокументировано**) + `uninstall` (**data-safe**: `podman secret rm` + снятие PATH-строки +
  том сносится только по второму подтверждению). Тесты: uninstall чистит секрет и PATH, том
  сохраняется без явного согласия.

### Стадия 3 — Supply-chain + инсталлер (**PR-3.1 параллелизуем с 1-го дня**)
- **PR-3.1 (CI/release, Б-1):** cosign-подпись в **`wallet-publish.yml`** (не docker-publish),
  + `id-token: write` (keyless), публикация digest. **Ручной laptop-publish фолбэк** (:13) —
  либо закрыть, либо signing-runbook (рекомендую: оставить break-glass, но runbook требует
  cosign-шаг). Предусловие: core-пакет публичным (ops). Тест: `cosign verify` в CI. Не зависит
  от Стадий 1-2.
- **PR-3.2:** `install.sh` (function-wrap, TLS-флаги, digest-пин, cosign-verify, установка шима,
  PATH, версионный URL, **публикация sha256 + строка про откат latest→vX**, инвариант «не
  касается секрета»). Тесты: shellcheck + прогон в чистом Linux-контейнере.

### Стадия 4 — Доки, листинги, релиз (Linux v1)
- **PR-4.1:** переписать INSTALL/TROUBLESHOOTING/SKILL/README под one-command; «inspect-before-run».
  Тест: греп-инвариант (0 упоминаний ручного `--name`/env-file-с-кавычками).
- **PR-4.2 (release + ops):** бамп, релиз-поезд (image-тег+digest, ClawHub, Smithery,
  mcp-publisher). Инсталлер живёт в репо (`scripts/install.sh`) — публикуется git-тегом,
  никакого хостинга; sha256 — в релиз-ноты тега.

### Стадия 5 — macOS / Apple Silicon (**fast-follow v1.1, Б-3**)
Отдельным решением после Linux-v1.
- **PR-5.1:** arm64-билд кошелька (`wallet-publish.yml platforms += linux/arm64`) + digest/подпись.
- **PR-5.2:** `doctor`/`install.sh` — ветка podman-machine (`init`/`start`, «machine не запущена»
  = отказ №1 на маке).
- **PR-5.3 (репо `homebrew-rustok`):** формула-tap (checksummed). Тест: `brew audit`/`brew test`.

## Ops Капитана (не мой код — чеклист в отчётах)

core-пакет GHCR публичным · cosign-identity + `id-token: write` · Smithery/mcp-publisher
листинги · Hermes-runbook (Стадия 0) · (v1.1) репо `homebrew-rustok`. **`get.rustok.org` из
v1 УБРАН** (инсталлер = GitHub raw по тегу) — домен позже редиректом, если понадобится бренд.

## Тест-план (сквозной, ужесточён — М-4)

«pty против образа» — необходимо, НЕ достаточно (всеядный e2e пропустил ОБА корня hotfix
v0.7.1). **Каждая PR-спека обязана нести строгие ассерты** (прецедент `assert_resident`):
точный JSON, записанный в MCP-конфиг; `claude mcp list → Connected`; **негативные контроли —
нет секрета → именованная ошибка, N>1 контейнеров → именованная ошибка, RPC-ключ отсутствует
в конфиге агента**. Классы: shell (shellcheck + bats на стабах), e2e (pty, secret-путь оба
движка), supply-chain (`cosign verify` в CI), docs (греп-инварианты). Инсталлер обязан иметь
СВОИ тесты — это и есть защита от повторения «первый пользователь всё сломал».

## Definition of Done (v1)

Все PR Стадий 0-4 смержены · образ подписан+digest-пин (wallet-publish) · `curl|sh` ставит
`rustok`, полный цикл `init/connect/console/update/uninstall` на чистой **Linux**-машине ·
доки без болячек · Hermes видит СВОЙ кошелёк по суб-метке · листинги на новой версии ·
трекер+human-plan+память освежены. **macOS/Homebrew — отдельный DoD Стадии 5.**

## Риски / что остаётся человеку (честно)

Не автоматизируем: ввод и офлайн-бэкап **seed-фразы и PIN**, пополнение адреса. Инсталлер
кончается на «кошелёк создан и подключён» — кастодия у человека. curl|sh-риск снят пятью
мерами + инвариантом «install.sh не касается секрета». podman file-driver = base64 (не
шифрование) — честно, апгрейд в бэклоге. Движок липкий (том per-engine).

## Замечено, не трогаю

Текущий `scripts/install.sh` (31 стр, печатальщик со стейл-дефолтом v0.6.0:7 и `--name`) —
заменяется PR-3.2, не патчится. `RUSTOK_MCP_API_KEY` (entrypoint:43-46, минтит эфемерный при
unset) — secret-миграция не трогает, PR не нужен (VERIFIED Ревьюером). Прецедент нумерации
листингов (0.4.x maintenance) — учесть в PR-4.2.
