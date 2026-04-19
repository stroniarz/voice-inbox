# Voice Inbox — Git Subtree Workflow

Voice Inbox jest rozwijany w monorepo `stroniarz-hq` pod `tools/voice-inbox/`, a publikowany jako osobny publiczny repo `github.com/stroniarz/voice-inbox` przez `git subtree split`.

## TL;DR — daily workflow

Pracuj normalnie w monorepo. Commituj zmiany w `tools/voice-inbox/` jak zwykle. Gdy chcesz opublikować do public repo:

```bash
./tools/voice-inbox/publish.sh
```

(Skrypt robi `subtree split` + push. Dokument opisuje co robi pod spodem.)

## Setup (one-time, już zrobione)

```bash
# 1. Utworzony public repo
gh repo create stroniarz/voice-inbox --public \
  --description "Lokalny audio-notyfikator na Maca — czyta Ci głosem nowe zadania z Linear"

# 2. Dodany remote
git remote add voice-inbox-pub https://github.com/stroniarz/voice-inbox.git

# 3. Pierwszy push
git subtree split --prefix=tools/voice-inbox --branch=voice-inbox-split
git push voice-inbox-pub voice-inbox-split:main
```

## Publikowanie zmian (powtarzalnie)

Z root `stroniarz-hq`, po commicie zmian w `tools/voice-inbox/`:

```bash
git subtree split --prefix=tools/voice-inbox --branch=voice-inbox-split
git push voice-inbox-pub voice-inbox-split:main
```

`subtree split` tworzy (lub aktualizuje) branch zawierający tylko historię z `tools/voice-inbox/`, bez reszty monorepo. Push wysyła to na `main` public repo.

## Zasady

- **NIGDY nie commituj bezpośrednio w public repo** — zawsze przez split + push z monorepo. Inaczej rozjazd historii.
- **Secrets** — `.env`, `config.yaml`, `*.db` są w `.gitignore` monorepo i `tools/voice-inbox/.gitignore`. Sprawdź przed push, czy nic wrażliwego nie wpadło. `config.example.yaml` to szablon bez sekretów.
- **PR-y z public** — jeśli ktoś otworzy PR na public repo, przenieś zmiany ręcznie do monorepo (git cherry-pick z remote) i dopiero wtedy zrób kolejny split + push. Subtree pull działa ale komplikuje historię.
- **License** — aktualnie brak pliku `LICENSE`. Do dodania przed opublikowaniem publicznego artykułu.

## Troubleshooting

**"Updates were rejected because the remote contains work that you do not have locally"**

Ktoś zmienił public repo bezpośrednio. Dwie opcje:

- (zalecane) Zobacz co tam wpadło, ręcznie przenieś zmiany do monorepo (lub odrzuć), potem force push:
  ```bash
  git push voice-inbox-pub voice-inbox-split:main --force
  ```
- (alternatywa) Subtree pull, ale miesza historię:
  ```bash
  git subtree pull --prefix=tools/voice-inbox voice-inbox-pub main --squash
  ```

**Subtree split jest bardzo wolny**

Dla większej historii można cache'ować:
```bash
git subtree split --prefix=tools/voice-inbox --branch=voice-inbox-split --rejoin
```
Flaga `--rejoin` zapisuje merge commit w monorepo żeby następny split był szybszy. Uwaga — dodaje commit do monorepo.

**Usunięcie lokalnego branch split**

```bash
git branch -D voice-inbox-split
```
Przy kolejnym `split` zostanie odtworzony z bieżącej historii.
