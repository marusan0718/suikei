import AVFoundation
import Combine

@MainActor
final class SuikeiAudioEngine: ObservableObject {
    @Published private(set) var isRunning = false
    @Published private(set) var routeName = "iPad"
    @Published var errorMessage: String?

    private let engine = AVAudioEngine()
    private let timePitch = AVAudioUnitTimePitch()
    private let reverb = AVAudioUnitReverb()

    private var sourceNode: AVAudioSourceNode?
    private var routeObserver: NSObjectProtocol?
    private var engineObserver: NSObjectProtocol?
    private var tremoloTimer: Timer?
    private var tremoloPhase = 0.0

    private var currentSpeedNorm = 0.5
    private var currentLevelCm = 120.0
    private var currentSlack = false
    private var baseOutputVolume: Float = 0.82

    init() {
        configureNotifications()
        refreshRouteName()
    }

    deinit {
        if let routeObserver {
            NotificationCenter.default.removeObserver(routeObserver)
        }
        if let engineObserver {
            NotificationCenter.default.removeObserver(engineObserver)
        }
    }

    func start() {
        guard !isRunning else { return }

        do {
            try configureAudioSession()

            if sourceNode == nil {
                buildGraph()
            }

            engine.prepare()
            try engine.start()

            isRunning = true
            errorMessage = nil
            refreshRouteName()
            applyTideParameters()
        } catch {
            errorMessage = "Audio start failed: \(error.localizedDescription)"
            isRunning = false
        }
    }

    func stop() {
        tremoloTimer?.invalidate()
        tremoloTimer = nil

        engine.pause()
        engine.mainMixerNode.outputVolume = 0
        isRunning = false

        do {
            try AVAudioSession.sharedInstance().setActive(
                false,
                options: [.notifyOthersOnDeactivation]
            )
        } catch {
            errorMessage = "Audio session stop failed: \(error.localizedDescription)"
        }
    }

    func setTide(speedNorm: Double, levelCm: Double, slack: Bool) {
        currentSpeedNorm = min(1, max(0, speedNorm))
        currentLevelCm = levelCm
        currentSlack = slack

        guard sourceNode != nil else { return }
        applyTideParameters()
    }

    private func configureAudioSession() throws {
        let session = AVAudioSession.sharedInstance()

        try session.setCategory(
            .playback,
            mode: .default,
            policy: .longFormAudio,
            options: []
        )

        try session.setActive(true)
        refreshRouteName()
    }

    private func buildGraph() {
        let format = AVAudioFormat(
            standardFormatWithSampleRate: 48_000,
            channels: 2
        )!

        let source = makeLayerOneSource(format: format)
        sourceNode = source

        engine.attach(source)
        engine.attach(timePitch)
        engine.attach(reverb)

        reverb.loadFactoryPreset(.largeHall2)
        reverb.wetDryMix = 24

        engine.connect(source, to: timePitch, format: format)
        engine.connect(timePitch, to: reverb, format: format)
        engine.connect(reverb, to: engine.mainMixerNode, format: format)

        engine.mainMixerNode.outputVolume = baseOutputVolume
    }

    private func makeLayerOneSource(format: AVAudioFormat) -> AVAudioSourceNode {
        let sampleRate = format.sampleRate

        // Layer 1 — simplified route-test version.
        // Frequencies preserve the completed Layer 1 tonal identity.
        let frequencies: [Double] = [
            220.46, 223.39, 216.80,
            433.59, 440.92, 446.78,
            879.64, 882.57,
            1759.28
        ]

        let amplitudes: [Double] = [
            0.74, 0.38, 0.24,
            0.11, 0.20, 0.29,
            0.08, 0.08,
            0.050
        ]

        let pans: [Double] = [
             0.00,  0.05, -0.05,
            -0.20,  0.06,  0.23,
            -0.47,  0.45,
             0.00
        ]

        var phases = Array(repeating: 0.0, count: frequencies.count)
        var sampleCursor: Int64 = 0

        return AVAudioSourceNode(format: format) {
            isSilence,
            _,
            frameCount,
            audioBufferList -> OSStatus in

            isSilence.pointee = false

            let buffers = UnsafeMutableAudioBufferListPointer(audioBufferList)
            guard buffers.count >= 2,
                  let left = buffers[0].mData?.assumingMemoryBound(to: Float.self),
                  let right = buffers[1].mData?.assumingMemoryBound(to: Float.self)
            else {
                return noErr
            }

            let frames = Int(frameCount)
            let breathPeriod = 1.32
            let twoPi = Double.pi * 2

            for frame in 0..<frames {
                let time = Double(sampleCursor) / sampleRate
                let breathPosition =
                    time.truncatingRemainder(dividingBy: breathPeriod) / breathPeriod

                let arch = max(0, sin(Double.pi * breathPosition))
                let smoothArch = arch * arch * (3 - 2 * arch)

                let breathNumber = Int(time / breathPeriod)
                let fifthBreath = (breathNumber % 5) == 4

                var leftSample = 0.0
                var rightSample = 0.0

                for index in frequencies.indices {
                    let oscillator = sin(phases[index])

                    var level = amplitudes[index]

                    // Upper clusters come forward gently every fifth breath.
                    if index >= 3 {
                        level *= fifthBreath ? 1.30 : 0.72
                    }

                    if index >= 6 {
                        level *= fifthBreath ? 1.16 : 0.64
                    }

                    let pan = pans[index]
                    let leftGain = sqrt((1 - pan) * 0.5)
                    let rightGain = sqrt((1 + pan) * 0.5)

                    leftSample += oscillator * level * leftGain
                    rightSample += oscillator * level * rightGain

                    phases[index] += twoPi * frequencies[index] / sampleRate
                    if phases[index] >= twoPi {
                        phases[index] -= twoPi
                    }
                }

                // Rounded, slightly submerged breathing.
                let envelope = 0.015 + 0.115 * smoothArch
                left[frame] = Float(leftSample * envelope)
                right[frame] = Float(rightSample * envelope)

                sampleCursor += 1
            }

            return noErr
        }
    }

    private func applyTideParameters() {
        let speed = currentSpeedNorm

        // Same design language as the web version:
        // slow tide ~0.78x, fast tide ~1.30x.
        let normalRate = 0.78 + speed * 0.52
        let rate = currentSlack ? normalRate * 0.64 : normalRate

        // About -12 ... +18 cents.
        let cents = (-12 + speed * 30) * (currentSlack ? 0.25 : 1.0)

        timePitch.rate = Float(max(0.50, min(1.35, rate)))
        timePitch.pitch = Float(cents)

        baseOutputVolume = currentSlack ? 0.65 : 0.82
        engine.mainMixerNode.outputVolume = baseOutputVolume

        configureTremolo()
    }

    private func configureTremolo() {
        tremoloTimer?.invalidate()
        tremoloTimer = nil
        tremoloPhase = 0

        guard isRunning, currentLevelCm > 150 else {
            engine.mainMixerNode.outputVolume = baseOutputVolume
            return
        }

        let strength = min(1, max(0, (currentLevelCm - 150) / 70))

        tremoloTimer = Timer.scheduledTimer(
            withTimeInterval: 0.05,
            repeats: true
        ) { [weak self] _ in
            guard let self else { return }

            Task { @MainActor in
                self.tremoloPhase += 0.05 * 2 * Double.pi * 0.70
                let modulation =
                    1 + 0.045 * strength * sin(self.tremoloPhase)

                self.engine.mainMixerNode.outputVolume =
                    self.baseOutputVolume * Float(modulation)
            }
        }
    }

    private func configureNotifications() {
        let center = NotificationCenter.default

        routeObserver = center.addObserver(
            forName: AVAudioSession.routeChangeNotification,
            object: AVAudioSession.sharedInstance(),
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                self?.refreshRouteName()
            }
        }

        engineObserver = center.addObserver(
            forName: .AVAudioEngineConfigurationChange,
            object: engine,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in
                guard let self, self.isRunning else { return }

                do {
                    self.engine.prepare()
                    try self.engine.start()
                    self.refreshRouteName()
                } catch {
                    self.errorMessage =
                        "Audio route restart failed: \(error.localizedDescription)"
                }
            }
        }
    }

    private func refreshRouteName() {
        let outputs = AVAudioSession.sharedInstance().currentRoute.outputs

        if outputs.isEmpty {
            routeName = "出力先なし"
            return
        }

        routeName = outputs
            .map(\.portName)
            .joined(separator: " + ")
    }
}
