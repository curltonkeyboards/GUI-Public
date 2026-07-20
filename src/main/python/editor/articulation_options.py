# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared helpers for building Articulation / velocity-curve dropdowns.

Every Articulation combo in the GUI should look and behave like the reference
"Channel Articulations" tab:

  * Factory presets (indices 0-22) always listed.
  * A greyed, non-selectable "User Articulations" divider followed by the 50
    user slots (23-72) -- but user slots that are NOT configured on the device
    are hidden.
  * Greyed "CC Articulations" / "AT Articulations" dividers with the AT/CC mode
    band (73-98) -- shown only when that band is enabled on the device.

To keep any device index round-trippable (a device sitting on a hidden index
must still display + save correctly), we never REMOVE rows from a zone/per-key
combo: populate_articulation_combo() builds the full model once, and
apply_articulation_visibility() hides/shows rows in the popup view. The currently
selected index is always kept visible.
"""

FACTORY_ARTIC_NAMES = [
    "Softest", "Soft", "Basic", "Hard", "Hardest",
    "Soft Leg", "Basic Leg", "Hard Leg", "Sens Leg",
    "Fixed Vol", "Drums Easy", "Drums Soft", "Drums Basic", "Drums Hard",
    "Sensitive Soft", "Sensitive", "Sensitive Hard", "Drums Sens",
    "Ultra Sens", "Fixed Sens", "Two Toned", "Reverse",
    "Random Highlights",
]

FACTORY_COUNT = len(FACTORY_ARTIC_NAMES)          # 23
USER_COUNT = 50
USER_START = FACTORY_COUNT                          # 23
ATCC_START = FACTORY_COUNT + USER_COUNT             # 73
ATCC_PER_FLAVOR = 13
ATCC_COUNT = ATCC_PER_FLAVOR * 2                    # 26
ATCC_END = ATCC_START + ATCC_COUNT - 1             # 98

# 13 base AT/CC mode names (73-85 = CC flavor, 86-98 = poly-AT flavor). Kept in
# sync with the firmware ATCC_MODE_NAMES / velocity_tab ATCC_NAMES.
ATCC_BASE_NAMES = [
    "Leg Vib Slow", "Leg Vib Fast", "Leg Vib Smooth",
    "Vib Slow", "Vib Fast", "Vib Smooth",
    "Fast Swell", "Slow Swell", "Reverse Swell",
    "Fast Fall", "Slow Fall", "Shimmer Me", "Shimmer Leg",
]

DIVIDER_USER = "─── User Articulations ───"
DIVIDER_CC = "─── CC Articulations ───"
DIVIDER_AT = "─── AT Articulations ───"


def user_slot_label(user_names, i):
    if user_names and i < len(user_names) and user_names[i]:
        return user_names[i]
    return "User {}".format(i + 1)


def _add_divider(combo, label):
    combo.addItem(label)
    row = combo.count() - 1
    item = combo.model().item(row)
    if item is not None:
        item.setEnabled(False)      # greyed, non-selectable
    return row


def populate_articulation_combo(combo, user_names=None, include_none=False,
                                none_label="None", none_index=255):
    """Build the FULL articulation model on `combo`:

        [None] + factory(0-22) + [User divider] + user(23-72)
               + [CC divider] + CC band(73-85) + [AT divider] + AT band(86-98)

    All rows are always present so any device index round-trips; visibility is
    controlled by apply_articulation_visibility(). Stores layout metadata on the
    combo as `_artic_meta`. Signals are blocked while (re)building."""
    blocked = combo.blockSignals(True)
    try:
        combo.clear()
        meta = {
            'user_rows': {}, 'cc_rows': [], 'at_rows': [],
            'user_divider_row': None, 'cc_divider_row': None, 'at_divider_row': None,
        }
        if include_none:
            combo.addItem(none_label, none_index)
        for i, name in enumerate(FACTORY_ARTIC_NAMES):
            combo.addItem(name, i)

        meta['user_divider_row'] = _add_divider(combo, DIVIDER_USER)
        for i in range(USER_COUNT):
            combo.addItem(user_slot_label(user_names, i), USER_START + i)
            meta['user_rows'][i] = combo.count() - 1

        meta['cc_divider_row'] = _add_divider(combo, DIVIDER_CC)
        for i in range(ATCC_PER_FLAVOR):
            combo.addItem("{} (CC)".format(ATCC_BASE_NAMES[i]), ATCC_START + i)
            meta['cc_rows'].append(combo.count() - 1)

        meta['at_divider_row'] = _add_divider(combo, DIVIDER_AT)
        for i in range(ATCC_PER_FLAVOR):
            combo.addItem("{} (Poly)".format(ATCC_BASE_NAMES[i]),
                          ATCC_START + ATCC_PER_FLAVOR + i)
            meta['at_rows'].append(combo.count() - 1)

        combo._artic_meta = meta
    finally:
        combo.blockSignals(blocked)
    return combo._artic_meta


def apply_articulation_visibility(combo, user_configured=None, cc_enabled=True,
                                  at_enabled=True, keep_index=None):
    """Hide unconfigured user slots and disabled AT/CC bands from the popup
    (without removing them from the model, so selection round-trips). The
    currently selected data index (keep_index, defaulting to the combo's current
    data) is always kept visible, as is each band's divider while any of its rows
    is visible."""
    meta = getattr(combo, '_artic_meta', None)
    if meta is None:
        return
    view = combo.view()
    if keep_index is None:
        keep_index = combo.currentData()

    def set_hidden(row, hidden):
        if row is None:
            return
        try:
            view.setRowHidden(row, bool(hidden))
        except Exception:
            pass

    # User slots (hide unconfigured)
    any_user = False
    for i, row in meta['user_rows'].items():
        idx = USER_START + i
        if user_configured is None:
            configured = True
        else:
            configured = i < len(user_configured) and bool(user_configured[i])
        visible = configured or (keep_index == idx)
        set_hidden(row, not visible)
        any_user = any_user or visible
    set_hidden(meta['user_divider_row'], not any_user)

    # CC band (hide when CC modes disabled)
    any_cc = False
    for k, row in enumerate(meta['cc_rows']):
        idx = ATCC_START + k
        visible = bool(cc_enabled) or (keep_index == idx)
        set_hidden(row, not visible)
        any_cc = any_cc or visible
    set_hidden(meta['cc_divider_row'], not any_cc)

    # AT band (hide when AT modes disabled)
    any_at = False
    for k, row in enumerate(meta['at_rows']):
        idx = ATCC_START + ATCC_PER_FLAVOR + k
        visible = bool(at_enabled) or (keep_index == idx)
        set_hidden(row, not visible)
        any_at = any_at or visible
    set_hidden(meta['at_divider_row'], not any_at)


def select_articulation_index(combo, index):
    """Set the combo's current selection to the row whose data == index, with
    signals blocked. Returns True on success."""
    if index is None:
        return False
    blocked = combo.blockSignals(True)
    try:
        for i in range(combo.count()):
            if combo.itemData(i) == index:
                combo.setCurrentIndex(i)
                return True
    finally:
        combo.blockSignals(blocked)
    return False
