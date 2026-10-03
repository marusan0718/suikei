# Suikei Native — AirPlay 2 / HomePod prototype

This folder is a **native iPad prototype** for Suikei.
It does not replace or modify the published web UI at `https://marusan0718.github.io/suikei/`.

## Goal of this phase

Verify this chain first:

```
real-time synthesis
  -> AVAudioEngine
  -> AVAudioSession(.playback, .longFormAudio)
  -> AVRoutePickerView
  -> HomePod / AirPlay 2
```

The prototype synthesizes a simplified **Layer 1** in real time. It is not a rendered audio file.

## Test

1. Open `SuikeiNative.xcodeproj` in Xcode.
2. Select your development team under Signing & Capabilities.
3. Run it on a physical iPad.
4. Tap the AirPlay route button.
5. Select a HomePod.
6. Tap **再生**.
7. Move **潮流速度** from 0% to 100%.
   - motion rate changes in real time
   - pitch moves roughly from -12 to +18 cents
8. Turn **潮止まり** on/off.
9. Raise **潮位** above 150 cm to enable a subtle tremolo.

## Why native

Safari Web Audio can synthesize Suikei correctly, but routing that Web Audio graph to HomePod is not reliable.
This prototype uses Apple's native audio route:
`AVAudioEngine + AVAudioSession.RouteSharingPolicy.longFormAudio`.

## Next phase

After HomePod routing is confirmed on the target iPad:

- port Layer 2–6
- preserve the final mix:
  - L1 0.295
  - L2 0.525
  - L3 0.108
  - L4 0.395
  - L5 0.175
  - L6 0.380
- connect live tide data
- connect Morning / Afternoon / Evening / Night
- reuse the existing Suikei visual UI with a native audio bridge
