# Keycode Naming Review — for Head of Marketing

**From:** Engineering (GUI/firmware)
**Date:** 2026-07-18
**Status:** All keys below are now live in the configurator with *engineering placeholder names*. Every key on the keyboard is now searchable in the Advanced Keys section. **We need final customer-facing names before ship** — the placeholder names appear on key labels, tooltips, and in search, and can be changed freely (only the display text changes; saved user layouts are unaffected).

A pre-ship audit found a set of firmware features that were fully working on the keyboard but either missing from the configurator entirely, or present without a name (so they could not be found in search or assigned to a key). They are grouped below by how much naming attention they need.

---

## 1. The headline feature — "Mod Press" (needs a real product name)

**What it is:** A new kind of analog expression control, unique to our Hall-effect hardware. The user assigns one or more "Mod Press" keys anywhere on a layer, each tied to a MIDI CC (0–127). These keys play **no notes**. Instead, while held, the keyboard continuously measures **how deep each of them is pressed** and combines every Mod Press key on the active layer that targets the same CC into **one smooth controller value**:

- Press one of them halfway → the CC sits at half of its share.
- The firmware detects how many of the keys are mapped on the current layer and scales automatically: each key contributes up to `127 / N`, summing the depths of all of them — press all of them fully and the CC hits maximum (127).
- Release → the value falls back to 0. Switching layers cleanly zeroes the CC.

In practice this turns any strip of keys into a **finger-pressure fader / expression pad**: two keys = a two-finger swell control, a whole row = a giant afterglow-style modulation surface. It works with any CC (mod wheel, filter cutoff, expression, breath…).

- **Count:** 128 keys (one per MIDI CC), keycodes `0xF300–0xF37F`.
- **Current placeholder:** key label `ModPrs CC{n}`, listed in Advanced Keys under the "Mod Press" selector (type a CC number).
- **Naming decision needed:** the feature name itself. Engineering has been calling it "Mod Press". Ideas to react to (not prescriptions): *Pressure Pad*, *Expression Pad*, *Depth Fader*, *Flex Keys*, *PolyPress*. The name will appear as the category in the Advanced Keys search and on the key labels.

---

## 2. On-device menu keys (previously impossible to assign from the GUI)

Three "settings keys" open menus on the keyboard's built-in screen. The firmware has supported them all along; until now the configurator had no entry for them, so users could never bind them to a key.

| Keycode | Placeholder label | What it opens |
|---|---|---|
| `0xCA24` | **Settings Menu** | The full on-device settings menu (the same one reachable by the dedicated settings keycode today) |
| `0xCA25` | **Load Preset Menu** | A quick picker that loads a saved settings preset, then closes itself |
| `0xCA26` | **Playing Style Editor** | The on-device velocity-preset ("playing style") editor |

**Naming decision needed:** what we call these three menus in customer language — especially whether "Playing Style" is the term we're shipping for velocity presets (the GUI already uses "playing style" in some tooltips, and "Touch Dial Dynamics (playing style)" elsewhere). These names should match the printed quick-start guide.

---

## 3. Arpeggiator modes (two new keys + a naming clean-up)

The firmware has **five** arpeggiator modes; the GUI previously showed only three, and two of those were mislabeled. All five are now shown with corrected labels:

| Keycode | Firmware behavior | New GUI label (placeholder) |
|---|---|---|
| `0xEE24` | Single note, synced to the beat | Arp Mode / Single / Synced |
| `0xEE25` | Single note, free-running | Arp Mode / Single / Unsync |
| `0xEE26` | Chord, synced (all held notes each step) | Arp Mode / Chord / Synced |
| `0xEE27` | **NEW to GUI** — chord, unsynced (each held note runs its own timing) | Arp Mode / Chord / Unsync |
| `0xEE28` | **NEW to GUI** — chord "advanced": rotates through held notes at the base rate | Arp Mode / Chord / Rotation |

**Naming decision needed:** customer-facing names for the five modes, particularly `0xEE28` — firmware calls it "Chord Advanced", but "Advanced" says nothing about what it does (it cycles/rotates the held notes). Engineering placeholder is "Chord Rotation". Options: *Rotate*, *Cycle*, *Roll*, *Spread*.

---

## 4. Looper / performance keys that had no name

| Keycode | Placeholder label | What it does |
|---|---|---|
| `0xCC21` | **Octave Modifier** | Hold it, then tap a loop key: toggles that loop's octave-doubler. (The per-loop octave keys were already named; this modifier button was not findable.) |
| `0xEF88` | **Clear Hold** | Hold it — the screen shows "Press Loop/Seq to Clear" — then press any loop or sequencer key to erase it. A safer, deliberate way to clear. |

**Naming decision needed:** short names that fit a 3-line keycap label. "Clear Hold" reads awkwardly; alternatives: *Clear Mode*, *Eraser*, *Clear + Pick*.

---

## 5. Ear-trainer levels that were hidden

The interval trainer has three question styles per difficulty: ascending, descending, and **mixed (both directions)**. The mixed style existed in firmware but had no GUI keys. Four new keys:

| Keycode | Placeholder label | Behavior |
|---|---|---|
| `0xC92C` | Basic Intervals / Up+Down | Intervals up to a fifth, either direction |
| `0xC92F` | Octave Intervals / Up+Down | Intervals up to an octave, either direction |
| `0xC932` | Extended Intervals / Up+Down | Intervals one to two octaves, either direction |
| `0xC935` | All Intervals / Up+Down | Everything up to two octaves, either direction |

**Naming decision needed:** the existing keys are named "…Level 1 / Level 2 / Level 3" (which actually mean up / down / simultaneous — not difficulty levels). Marketing may want to rename the whole family coherently, e.g. *Ascending / Descending / Mixed / Harmonic*.

---

## 6. Quick Build slots that grew (rubber-stamp naming)

These follow the existing naming pattern; flagging for awareness only:

- **SmartChord Quick Build slots 9–20** (`0xF132–0xF13D`) — the chord builder now has 20 slots; the GUI previously exposed 8.
- **Dynamic Chord Quick Build slots 5–8** (`0xF184–0xF187`) — grew from 4 to 8.

Labels continue the pattern ("Chord 9 Quick Build" … "DynC 8 Quick Build"). No decision needed unless the "Quick Build" brand name is changing.

---

## Also fixed in this pass (no naming input needed)

- The arpeggiator preset browser mislabeled factory patterns: it split the list as "48 factory / 40 user" while the shipping firmware has **119 factory rhythm patterns + 40 user presets**. Keys 48–87 were shown as "User Presets" but actually triggered factory patterns. The browser now shows the correct 119/40 split.
- Two keycodes were deliberately **not** exposed: `0xCC48` (dead — reserved slot for a removed feature) and `0xC936–0xC937` (dispatch dead-ends in firmware, they do nothing).

## What we need back from Marketing

1. A product name for the **Mod Press** feature (item 1) — highest priority; it's the marquee item.
2. Confirmed names for the three **on-device menu keys** (item 2), aligned with the manual.
3. The five **arp mode** names (item 3).
4. Short names for **Octave Modifier** and **Clear Hold** (item 4).
5. A decision on the **ear-trainer family** naming scheme (item 5).

Once names are decided, engineering will update the labels/tooltips in one pass — it's a text-only change with no compatibility impact.
