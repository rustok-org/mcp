# Disclaimer

This software is provided **as is**, without warranty of any kind, under the
[MIT-0 license](LICENSE). It is experimental software that holds real private
keys and can move real funds on live networks, including Ethereum mainnet.

## It is not advice

Nothing this wallet, or an agent driving it, produces is investment, accounting,
legal, or tax advice, or a recommendation to buy, sell, or hold anything.

## What an agent does with this wallet is not an act of the authors

The wallet executes what the operator of the machine authorizes. The agent
driving it is third-party software whose output is unpredictable and may be
inaccurate, incorrect, or undesirable. Evaluating each proposed transaction
before approving it is the user's exclusive responsibility.

## The safeguards are narrow — here is every limit

- **There are no spending limits.** No budget, no per-transaction cap. A wallet
  holds what its owner puts on it, and every last unit of that is reachable.
- **txguard flags risky transactions; it does not block them.** A flag is
  information for the human at the console, not a refusal.
- **Autonomous mode, once confirmed, sends without asking again.** The
  confirmation is given once per wallet, at the console, by the user. After it,
  no per-transaction approval is requested.
- **`sign_message` is not console-gated.** It returns a signature without the
  approval window. It refuses a raw hex blob, but it signs an ordinary plaintext
  message. The console boundary covers sending funds; it does not cover signing.

An agent reads untrusted data — token names, web pages, contract metadata — and
that data can induce it to propose a transaction, or a message to sign, that the
user did not intend. The console approval step stops the first and not the
second, and it works only if the user reads what they approve.

## Self-custody means no recovery

Nobody — not the authors, not any support channel — can restore a lost mnemonic,
reverse a signed transaction, or recover funds sent to the wrong address.

## Verify what you install

Install only at the published image digest, through the installer that pins it.
A substituted image would reach the same volume the private keys live in.

## Risk

The risk of loss through use of this software can be substantial, and the user
assumes any and all risks of loss and liability arising from its use. Users are
responsible for complying with the laws that apply to them.
