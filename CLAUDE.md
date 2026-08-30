# CLAUDE.md — this repo's knowledge base lives elsewhere

**This repository is PUBLIC. It deliberately carries no project knowledge base
and no internal design docs.**

The knowledge base for **this** repo, and the design / analysis / audit
documents that used to sit in this root and in `docs/prelaunch-changes/`, are
kept in the **private `curltonkeyboards/vial-gui-custom` repo**, under:

```
vial-gui-custom/gui-public/
├── CLAUDE.md      <- the knowledge base for THIS repo — read this first
├── README.md      <- what the folder is and the working rules
└── ...            <- the internal design / analysis / audit docs
```

They live there because they describe internal firmware behaviour, EEPROM
memory maps, HID command layouts and unreleased work — none of which belongs in
a public repository.

## If you are working on this repo

1. **Read `vial-gui-custom/gui-public/CLAUDE.md` first.** Treat it exactly as
   you would a knowledge base sitting in this root: it carries the project
   overview, the GUI↔firmware wire formats, and the running record of changes.
2. **Record your change there too**, not here.
3. **Do not copy any of `gui-public/` into this repo.** Keeping it out is the
   point of the arrangement.

Both repos are normally checked out together, so that path should already be
available. If it is not, ask for access to `vial-gui-custom` before making
changes that depend on firmware behaviour — the two are developed in lockstep
and the wire formats have to match.
