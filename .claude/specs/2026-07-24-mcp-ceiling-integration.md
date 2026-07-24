# Спека: MCP ceiling integration (инкремент 1, MCP-сторона)

- **Дата:** 2026-07-24 · Инженер: Kimi · Статус: DRAFT на Гейт-1 (компактная, по аудиту B1/I1)
- **Связь:** core PR #96 (policy_mode в WalletContext) · Аудит `~/Dev/rustok-wallet-mcp-audit-report.md` (B1, I1)

## Цель

Замкнуть B1 end-to-end: MCP читает потолок из core, а клиентский `initialize` может только СУЗИТЬ выданное (никогда не расширить). Плюс два мелких фикса из аудита: enum eip712 и дырка второго initialize на SSE.

## Скоуп

1. **B1 (stdio):** `handle_initialize` — `granted = seeded & client_caps` (было: замена). Seeded = env `RUSTOK_MCP_CAPABILITIES` или all.
2. **Потолок из core:** при initialize MCP читает `wallet_context` через gateway (`policy_mode`, core PR #96) и дополнительно пересекает с потолком режима:
   - `read_only` → `{read_wallet, preview_tx}`
   - `supervised` / `autonomous` → все capabilities (семантика инкр.1)
   - gateway недоступен/поле отсутствует → только seeded + warning (фильтрация в MCP — advisory; enforcement — в core). Потолок режима НИКОГДА не расширяет seeded.
3. **I1 (часть):** из `sign_message` inputSchema убрать `"eip712"` из enum (описание говорит «not supported»; сам инструмент в инкр.1 всё равно отклоняется core).
4. **SSE-дырка:** guard `not session.capabilities` (falsy пустой сет пропускает второй initialize) → явный флаг `session.initialized`; capabilities ставятся один раз на сессию.

## Вне скоупа

- Инкремент 2/3 (autonomous-исполнение, set_policy, kind:sign).
- Фильтрация tools/list по режиму сверх пересечения capabilities (получается бесплатно из has_capability).
- Остальные находки аудита (I3 annotations, I4 маскировка ошибок, I5/I6/I7/I8/I9) — отдельные задачи.

## Тесты

- B1 regression: seeded={read_wallet}, клиент просит все → получает {read_wallet}; сужение работает (подмножество сохраняется).
- Потолок режима: read_only → execute/sign скрыты в tools/list, preview виден; gateway недоступен → fallback к seeded + warning.
- SSE: второй initialize не меняет session.capabilities.
- enum sign_message == ["eip191"].
- Существующие зелёные не сломаны (`pytest`), `ruff check`, CHANGELOG-запись.
