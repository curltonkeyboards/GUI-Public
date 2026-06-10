# Aftertouch Methods Analysis: orthomidi5x14 vs Wooting Analog MIDI

## Executive Summary

This document compares the aftertouch implementations in the orthomidi5x14 Hall effect keyboard firmware against the Wooting analog MIDI implementation. Key findings:

- **orthomidi5x14**: 4 configurable modes using CC messages with robust noise filtering
- **Wooting**: Simple linear mapping using true MIDI Polyphonic Aftertouch messages

---

## orthomidi5x14 Implementation

### Location
- Main processing: `quantum/matrix.c:762-816` (process_midi_key_analog function)
- CC sending: `quantum/matrix.c:810`
- Configuration: `keyboards/orthomidi5x14/orthomidi5x14.c:2205-2209`

### Aftertouch Modes

| Mode | Name | Description | Formula | Activation |
|------|------|-------------|---------|------------|
| **0** | Off | Disabled | N/A | N/A |
| **1** | Reverse | Inverted key position - pressure decreases as key goes down | `127 - (travel * 127) / 240` | Requires pedal |
| **2** | Bottom-out | Direct key position - pressure increases with depth | `(travel * 127) / 240` | Requires pedal |
| **3** | Post-Actuation | Only measures travel beyond actuation point | `((travel - threshold) * 127) / range` | Always active |
| **4** | Vibrato | Measures movement speed/oscillation | `min((delta * 100) / time, 127)` | Above actuation |

### Implementation Details

```c
// From quantum/matrix.c:762-816
switch (aftertouch_mode) {
    case 1:  // Reverse
        if (aftertouch_pedal_active) {
            aftertouch_value = 127 - ((travel * 127) / 240);
            send_aftertouch = true;
        }
        break;

    case 2:  // Bottom-out
        if (aftertouch_pedal_active) {
            aftertouch_value = (travel * 127) / 240;
            send_aftertouch = true;
        }
        break;

    case 3:  // Post-actuation
        if (travel >= normal_threshold) {
            uint8_t additional_travel = travel - normal_threshold;
            uint8_t range = 240 - normal_threshold;
            if (range > 0) {
                aftertouch_value = (additional_travel * 127) / range;
                send_aftertouch = true;
            }
        }
        break;

    case 4:  // Vibrato
        if (travel >= normal_threshold) {
            uint16_t time_delta = now - state->last_time;
            uint8_t travel_delta = abs((int)travel - (int)state->last_travel);
            if (time_delta > 0 && travel_delta > 0) {
                uint8_t movement_speed = (travel_delta * 100) / time_delta;
                aftertouch_value = (movement_speed > 127) ? 127 : movement_speed;
                send_aftertouch = true;
            }
        }
        break;
}

// Hysteresis filter to reduce noise
if (send_aftertouch && abs((int)aftertouch_value - (int)state->last_aftertouch) > 2) {
    midi_send_cc(&midi_device, channel_number, aftertouch_cc, aftertouch_value);
    state->last_aftertouch = aftertouch_value;
}
```

### Noise Filtering Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ORTHOMIDI5X14 NOISE FILTERING PIPELINE                    │
└─────────────────────────────────────────────────────────────────────────────┘

    ADC Raw      EMA Filter      LUT Linear     Distance      Hysteresis
    (12-bit)  →  (α = 1/16)  →  (correction) →  (0-255)   →   (Δ > 2)
       │             │               │              │             │
       │             │               │              │             ▼
       │             │               │              │        Aftertouch
       │             │               │              │          Value
       │             │               │              │
       └──────┬──────┘               │              │
              │                      │              │
    Reduces high-freq        Compensates Hall      │
    ADC jitter              effect non-linearity   │
                                                   │
                                    ┌──────────────┘
                                    │
                            Only changes > 2
                            trigger new message
```

**Key noise reduction features:**
1. **EMA Filter** (matrix.c:37-39): `alpha = 1/16 = 0.0625` - Strong smoothing
2. **LUT Linearization** (matrix.c:262-266): Corrects Hall effect sensor curve
3. **Hysteresis** (matrix.c:808): Requires change > 2 to send message

---

## Wooting Analog MIDI Implementation

### Source
Repository: https://github.com/WootingKb/wooting-analog-midi
File: `wooting-analog-midi-core/src/lib.rs`

### Polyphonic Aftertouch Implementation

```rust
fn polyphonic_aftertouch(
    &mut self,
    note_id: NoteID,
    pressure: f32,
    channel: Channel,
) -> Result<()> {
    self.send(&[
        POLY_AFTERTOUCH_MSG | channel,  // 0xA0 | channel
        note_id,
        (f32::min(pressure, 1.0) * 127.0) as u8,
    ])?;
    Ok(())
}
```

### Key Characteristics

| Aspect | Value |
|--------|-------|
| Message Type | True MIDI Polyphonic Aftertouch (0xA0) |
| Pressure Mapping | Linear: `pressure * 127.0` |
| Trigger Condition | `new_value != previous_value` |
| Noise Filtering | Relies on SDK-level filtering |
| Refresh Rate | 100 Hz (10ms intervals) |
| Note Range | 21-108 (MIDI standard piano range) |

### Velocity Calculation (For Reference)

```rust
let duration = prev_time.elapsed().as_secs_f32();
self.velocity = f32::min(
    f32::max(
        ((new_value - prev_depth) / duration) * (note_config.velocity_scale() / 100.0),
        0.0,
    ),
    1.0,
);
```

- **Formula**: `(depth_change / time_elapsed) × (velocity_scale / 100.0)`
- **Default velocity_scale**: 5.0
- **Range**: Clamped 0.0-1.0, converted via `velocity * 127.0`

---

## Detailed Comparison

### Message Type

| orthomidi5x14 | Wooting |
|---------------|---------|
| CC Message (configurable CC#) | True Poly Aftertouch (0xA0) |
| `midi_send_cc(&device, ch, cc, val)` | `[0xA0 \| ch, note, pressure]` |

**Implications:**
- **CC Approach**: Single controller for all keys, synths need CC→aftertouch mapping
- **Poly AT Approach**: Native per-note control, better MPE/polyphonic synth support

### Noise Susceptibility

| Aspect | orthomidi5x14 | Wooting |
|--------|---------------|---------|
| ADC Filtering | EMA (α=1/16) + LUT | SDK-level (not visible) |
| Change Threshold | >2 required | Any change (0.01 reset) |
| Implicit Deadzone | Mode 3 (post-actuation) | None |
| Refresh Rate | ~1kHz (per scan) | 100 Hz |

**orthomidi5x14 advantages:**
1. Strong EMA smoothing removes high-frequency noise
2. Hysteresis prevents "chatter" from micro-variations
3. Mode 3 has built-in deadzone (only above actuation)
4. Mode 4 requires movement, not static value

**Wooting advantages:**
1. Lower 100Hz rate acts as implicit low-pass
2. 0.01 threshold for velocity reset provides some filtering
3. Simpler implementation (less processing overhead)

### Mode Comparison

| orthomidi5x14 Mode | Closest Wooting Equivalent | Notes |
|--------------------|---------------------------|-------|
| Mode 2 (Bottom-out) | Default linear | Direct mapping |
| Mode 1 (Reverse) | None | Unique feature |
| Mode 3 (Post-Actuation) | None | Most musical for AT |
| Mode 4 (Vibrato) | None | Unique feature |

---

## Mode Analysis

### Mode 1: Reverse (Inverted Pressure)

```
Travel (0-240) ──────────────────────────────────────►

Aftertouch
(0-127)
  127 ┤●
      │ ╲
   95 ┤  ╲
      │   ╲
   63 ┤    ╲
      │     ╲
   31 ┤      ╲
      │       ╲
    0 ┤────────●
      └─────────────────────────────────────────────
           0       60      120     180     240
                      Key Travel

Formula: AT = 127 - (travel × 127) / 240
```

**Use case**: Expression that fades out as key is pressed deeper. Useful for:
- Fading vibrato intensity
- Reverse dynamics effects
- Creative sound design

### Mode 2: Bottom-out (Direct Pressure)

```
Travel (0-240) ──────────────────────────────────────►

Aftertouch
(0-127)
  127 ┤                              ●
      │                            ╱
   95 ┤                          ╱
      │                        ╱
   63 ┤                      ╱
      │                    ╱
   31 ┤                  ╱
      │                ╱
    0 ┤●──────────────
      └─────────────────────────────────────────────
           0       60      120     180     240
                      Key Travel

Formula: AT = (travel × 127) / 240
```

**Use case**: Standard aftertouch behavior. More pressure = more effect. Similar to Wooting.

### Mode 3: Post-Actuation (Most Musical)

```
Travel (0-240) ──────────────────────────────────────►

Aftertouch                        Actuation Point (80)
(0-127)                                  │
  127 ┤                                  │         ●
      │                                  │       ╱
   95 ┤                                  │     ╱
      │                                  │   ╱
   63 ┤                                  │ ╱
      │                                  ╱
   31 ┤                              ╱ │
      │  DEADZONE                 ╱   │
    0 ┤────────────────────────●──────┴──────────────
      └─────────────────────────────────────────────
           0       60      120     180     240
                      Key Travel

Formula: AT = ((travel - threshold) × 127) / (240 - threshold)
```

**Use case**: Separates velocity from aftertouch. Key travel up to actuation = velocity, travel beyond = aftertouch. Most intuitive for musicians.

**Advantages:**
- Built-in deadzone eliminates noise near key rest
- Clear separation between initial strike and sustained pressure
- Matches acoustic piano pedal behavior

### Mode 4: Vibrato (Unique Feature)

```
Time ──────────────────────────────────────────────►

Travel              ●       ●       ●
                   ╱ ╲     ╱ ╲     ╱ ╲
                  ╱   ╲   ╱   ╲   ╱   ╲
                 ╱     ╲ ╱     ╲ ╱     ╲
                ╱       ●       ●       ╲
               ╱                         ╲

Aftertouch     ┌─┐     ┌─┐     ┌─┐
(0-127)        │ │     │ │     │ │
               │ │     │ │     │ │
               │ │     │ │     │ │
            ───┘ └─────┘ └─────┘ └──────

Formula: AT = min((Δtravel × 100) / Δtime, 127)
```

**Use case**: Detects finger "wiggle" on key for vibrato effect. Unique to orthomidi5x14.

**Characteristics:**
- Measures movement RATE, not position
- Faster wiggle = higher value
- Static press = zero output
- Natural noise immunity (noise is random, not oscillatory)

---

## Noise Analysis by Mode

### Mode 1 & 2 (Position-Based)

```
               Noise Impact Spectrum

High ┤
     │    ●    ← ADC noise (high freq) - Filtered by EMA
     │   ╱│
     │  ╱ │
     │ ╱  │    ● ← Mechanical vibration - Reduced by hysteresis
Med  ┤╱   │   ╱│
     │    │  ╱ │
     │    │ ╱  │    ● ← Temperature drift - Minimal (slow)
     │    │╱   │   ╱
Low  ┤    ●    │  ╱
     │         │ ╱
     │         │╱
     ┴─────────●──────────────────────────────────────
              Low        Med         High
                      Frequency
```

**Noise sources and mitigation:**
1. **ADC quantization noise**: EMA filter (α=1/16) provides ~12dB attenuation
2. **Mechanical vibration**: Hysteresis (>2) prevents message spam
3. **EMI pickup**: EMA smoothing

### Mode 3 (Post-Actuation)

```
               Noise Zone vs Active Zone

Aftertouch
(0-127)
  127 ┤                        ┌───── Active Zone ─────┐
      │                        │                       │
   95 ┤                        │    Aftertouch         │
      │                        │    responds           │
   63 ┤                        │                       │
      │                        │                       │
   31 ┤    Deadzone           │                       │
      │    (noise rejected)    │                       │
    0 ┤═════════════════════════────────────────────────
      └────────────────────────────────────────────────
           0      60     120    180     240
                     Actuation↑
                      Point
```

**Inherent noise immunity**: Any noise below actuation threshold is completely ignored.

### Mode 4 (Vibrato/Speed-Based)

```
               Random Noise vs Intentional Movement

               Random ADC Noise          Finger Vibrato
               (low correlation)         (high correlation)

            ●                               ●     ●
           ╱ ╲    ●                        ╱ ╲   ╱ ╲
          ╱   ╲  ╱        ●               ╱   ╲ ╱   ╲
    ●    ╱     ╲╱    ●   ╱ ╲             ╱     ●     ╲
     ╲  ╱              ╲ ╱   ╲    ●     ╱
      ╲╱                ●      ╲  ╱ ╲  ╱
                                ╲╱   ╲╱

    Average speed: LOW           Average speed: HIGH
    (random cancellation)        (consistent direction)
```

**Speed-based advantages:**
- Random noise has low average rate (cancels out)
- Intentional vibrato has consistent high rate
- Naturally distinguishes signal from noise

---

## Recommendations

### 1. Add True Polyphonic Aftertouch Mode

Your firmware already has the infrastructure (`midi_send_aftertouch_with_recording` in process_midi.c:656-660). Consider adding a Mode 5 that uses true poly AT:

```c
case 5:  // True Polyphonic Aftertouch
    if (travel >= normal_threshold) {
        uint8_t additional_travel = travel - normal_threshold;
        uint8_t range = 240 - normal_threshold;
        if (range > 0) {
            aftertouch_value = (additional_travel * 127) / range;
            send_poly_at = true;
        }
    }
    break;

// Send as poly AT instead of CC
if (send_poly_at && abs(aftertouch_value - state->last_aftertouch) > 2) {
    midi_send_aftertouch(&midi_device, channel, state->note_index, aftertouch_value);
    state->last_aftertouch = aftertouch_value;
}
```

### 2. Consider Wooting's Simple Approach for Default

For users who just want "more pressure = more effect", Wooting's simple linear mapping is intuitive. Your Mode 2 provides this, but requires pedal activation.

### 3. Keep Mode 4 (Vibrato) as Unique Feature

Wooting doesn't have this. It's genuinely useful for:
- Modwheel-like expression
- Real-time vibrato depth
- Dynamic filter modulation

### 4. Your Noise Filtering is Superior

Keep the current EMA + hysteresis approach. Wooting's implementation is simpler but potentially noisier.

---

## Conclusion

| Aspect | orthomidi5x14 | Wooting | Winner |
|--------|---------------|---------|--------|
| **Mode variety** | 4 modes | 1 mode | orthomidi5x14 |
| **Noise handling** | EMA + hysteresis | SDK-level | orthomidi5x14 |
| **Message type** | CC (configurable) | True Poly AT | Wooting |
| **Per-note control** | Limited (shared CC) | Full | Wooting |
| **Unique features** | Reverse, Post-Act, Vibrato | None | orthomidi5x14 |
| **Simplicity** | Complex | Simple | Wooting |

**Overall**: Your implementation is more feature-rich with better noise handling. The main improvement would be adding a true polyphonic aftertouch mode (using 0xA0 messages) for better synth compatibility while keeping your existing CC-based modes for flexibility.

---

## References

- orthomidi5x14 source: `quantum/matrix.c`, `keyboards/orthomidi5x14/orthomidi5x14.c`
- Wooting source: https://github.com/WootingKb/wooting-analog-midi
- Alternative Wooting implementation: https://github.com/simon-wh/WootingPiano
