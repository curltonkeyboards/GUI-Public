# Trigger Settings Overhaul - Implementation Summary

## Completed Changes

### Firmware (vial-qmk - ryzen)

#### 1. Data Structure Changes (`process_midi.h`)
- ✅ Changed `per_key_actuation_t.rapidfire_enabled` (uint8_t) to `flags` (uint8_t)
- ✅ Added `PER_KEY_FLAG_RAPIDFIRE_ENABLED` (Bit 0)
- ✅ Added `PER_KEY_FLAG_USE_PER_KEY_VELOCITY_CURVE` (Bit 1)
- ✅ Removed `LAYER_ACTUATION_FLAG_USE_PER_KEY_VELOCITY_CURVE` from layer structure
- ✅ Updated `DEFAULT_RAPIDFIRE_ENABLED` to `DEFAULT_PER_KEY_FLAGS`

#### 2. Matrix.c Updates
- ✅ Removed `per_key_mode_enabled` check from rapidfire logic (line 478)
- ✅ Removed `state->is_midi_key` check - rapidfire now works for ALL keys
- ✅ Updated to use `settings->flags & PER_KEY_FLAG_RAPIDFIRE_ENABLED` instead of `settings->rapidfire_enabled`

#### 3. Velocity Curve Logic (`orthomidi5x14.c`)
- ✅ Removed `layer_use_per_key_velocity_curve()` function
- ✅ Updated `get_key_velocity_curve()` to check per-key flag instead of layer flag
- ✅ Now checks `settings->flags & PER_KEY_FLAG_USE_PER_KEY_VELOCITY_CURVE`
- ✅ Works independently of `per_key_mode_enabled`

#### 4. HID Handlers (`orthomidi5x14.c`)
- ✅ Updated `handle_set_per_key_actuation()` to use `data[6]` as flags field
- ✅ Updated `handle_get_per_key_actuation()` to return flags in `response[4]`
- ✅ Updated `initialize_per_key_actuations()` to use `DEFAULT_PER_KEY_FLAGS`

### GUI (src/main/python)

#### 1. KeyboardWidget2 (`widgets/keyboard_widget.py`)
- ✅ Added `selected_keys` set for multi-selection
- ✅ Updated `mousePressEvent` to toggle selection (add if not selected, remove if selected)
- ✅ Updated `paintEvent` to highlight selected keys
- ✅ Added `select_all()`, `unselect_all()`, `invert_selection()` methods
- ✅ Added `get_selected_keys()` method

#### 2. Protocol Handling (`protocol/keyboard_comm.py`)
- ✅ Updated `set_per_key_actuation()` to send `settings.get('flags', 0)`
- ✅ Updated `get_per_key_actuation()` to receive `'flags': response[10]`
- ✅ Updated docstrings to document flags field

#### 3. Trigger Settings UI (`editor/trigger_settings.py`)
- ✅ Changed cache structure: `'rapidfire_enabled': 0` → `'flags': 0`
- ✅ Removed `'use_per_key_velocity_curve'` from `layer_data`
- ✅ Removed layer-level "Use Per-Key Velocity Curve" checkbox
- ✅ Added "Select All", "Unselect All", "Invert Selection" buttons
- ✅ Added per-key "Use Per-Key Velocity Curve" checkbox
- ✅ Added handlers: `on_select_all()`, `on_unselect_all()`, `on_invert_selection()`

## TODO: Remaining Work in trigger_settings.py

### Critical Updates Needed

1. **Update all `rapidfire_enabled` access to use flags**:
   - Search for `['rapidfire_enabled']` and replace with bit operations
   - Get rapidfire: `settings['flags'] & 0x01`
   - Set rapidfire on: `settings['flags'] |= 0x01`
   - Set rapidfire off: `settings['flags'] &= ~0x01`

2. **Update `on_use_per_key_curve_changed()` handler**:
   - Currently operates on layer-level, needs to be per-key
   - Should set/clear bit 1 of flags for selected keys
   - Use multi-selection: apply to all selected keys

3. **Update `on_rapidfire_toggled()` handler**:
   - Change from `settings['rapidfire_enabled'] = 1/0`
   - To: `settings['flags'] |= 0x01` or `settings['flags'] &= ~0x01`
   - Apply to all selected keys

4. **Update `on_key_clicked()` handler**:
   - Load settings for selected key(s)
   - Extract rapidfire from flags: `bool(settings['flags'] & 0x01)`
   - Extract per-key curve from flags: `bool(settings['flags'] & 0x02)`
   - Update UI checkboxes accordingly

5. **Update control enable/disable logic**:
   - Remove `mode_enabled` checks from rapidfire/deadzone/velocity curve controls
   - These should work regardless of per-key actuation mode
   - Only actuation slider should be gated by mode

6. **Implement multi-selection in all handlers**:
   - All value change handlers should apply to `get_selected_keys()`
   - Loop through selected keys and apply same value to all

### Example Code Patterns

```python
# Get rapidfire status from flags
rapidfire_on = bool(settings['flags'] & 0x01)

# Set rapidfire on
settings['flags'] |= 0x01

# Set rapidfire off
settings['flags'] &= ~0x01

# Get per-key velocity curve status
use_per_key_curve = bool(settings['flags'] & 0x02)

# Set per-key velocity curve on
settings['flags'] |= 0x02

# Set per-key velocity curve off
settings['flags'] &= ~0x02

# Apply to all selected keys
for key_widget in self.container.get_selected_keys():
    row, col = key_widget.desc.row, key_widget.desc.col
    key_index = row * 14 + col
    settings = self.get_key_settings(key_index)
    settings['flags'] |= 0x01  # Example: enable rapidfire
    self.send_key_settings(key_index, settings)
```

## Testing Checklist

Once all updates are complete, test:

- [ ] Multi-selection works (click to select, click again to deselect)
- [ ] Select All, Unselect All, Invert Selection buttons work
- [ ] Rapidfire works with per-key actuation disabled
- [ ] Deadzones work with per-key actuation disabled
- [ ] Per-key velocity curve checkbox works
- [ ] Changing any slider applies to all selected keys
- [ ] Firmware receives correct flags field (both bits)
- [ ] Settings persist to EEPROM correctly

